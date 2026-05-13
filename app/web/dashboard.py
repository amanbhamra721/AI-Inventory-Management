from fastapi import APIRouter, Request, HTTPException, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.services.db import get_db_connection, get_global_stats, get_stock_by_profile, get_stock_status_report
from app.services.auth import verify_password
import re
from typing import Optional
import io
import csv

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_current_user(request: Request):
    """Checks if the user has a valid session cookie."""
    user_phone = request.cookies.get("auth_user")
    if not user_phone:
        return None
    return user_phone


@router.get("/")
async def show_index(request: Request, search: Optional[str] = None):
    user_phone = request.cookies.get("auth_user")
    if not user_phone:
        return RedirectResponse(url="/login")

    # Fetch report, passing the search term if it exists
    stock_report = get_stock_status_report(user_phone, search_term=search)
    alerts = [item for item in stock_report if item['status'] != 'HEALTHY']
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stock_report": stock_report,
        "alerts": alerts,
        "search_query": search or "" # Pass the search back to UI
    })

@router.get("/export/csv")
async def export_inventory_csv(request: Request):
    """Generates a downloadable CSV of the current inventory."""
    user_phone = request.cookies.get("auth_user")
    if not user_phone:
        return RedirectResponse(url="/login")

    # Fetch the full, unfiltered report for export
    stock_report = get_stock_status_report(user_phone)

    # Build the CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write Headers
    writer.writerow(["Fabric", "Shade Code", "Current Meters", "Current Thaans", "Status"])
    
    # Write Data
    for item in stock_report:
        writer.writerow([
            item['fabric'], 
            item['shade_code'], 
            item['current_meters'], 
            item['current_thaans'], 
            item['status'].replace('_', ' ')
        ])

    output.seek(0)
    
    # Return as a downloadable file
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=live_inventory_report.csv"}
    )

@router.get("/inventory")
async def show_inventory(request: Request, phone: str = None):
    # Fetch Ledger History
    items = get_inventory_details(sender_phone=phone)
    
    return templates.TemplateResponse(
        "inventory.html", 
        {
            "request": request, 
            "items": items,
            "phone": phone
        }
    )

@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def handle_login(
    response: Response,
    phone: str = Form(...),
    password: str = Form(...)
):
    # --- 1. INPUT NORMALIZATION ---
    # Strip out any spaces, dashes, or + signs the user might have accidentally typed
    clean_phone = re.sub(r'\D', '', phone) 
    
    # If the user typed a 10-digit number, automatically prepend the '91' country code
    if len(clean_phone) == 10:
        clean_phone = f"91{clean_phone}"

    # --- 2. DATABASE LOOKUP ---
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # We now use 'clean_phone' instead of the raw 'phone' input
        cur.execute("SELECT phone_number, hashed_password, business_type FROM users WHERE phone_number = %s", (clean_phone,))
        user = cur.fetchone()
        
        if user and verify_password(password, user['hashed_password']):
            redirect = RedirectResponse(url="/", status_code=303)
            # Store the cleaned phone number in the cookie
            redirect.set_cookie(key="auth_user", value=clean_phone, httponly=True)
            return redirect
        
        return templates.TemplateResponse("login.html", {"request": {}, "error": "Invalid phone number or password."})
    finally:
        cur.close()
        conn.close()

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("auth_user")
    return response