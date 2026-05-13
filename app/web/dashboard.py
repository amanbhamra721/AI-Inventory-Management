from fastapi import APIRouter, Request, HTTPException, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, StreamingResponse
from app.services.db import get_db_connection, get_global_stats, get_stock_by_profile, get_stock_status_report, get_inventory_details
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

    # Fetch full report WITHOUT search for total calculations
    full_stock_report = get_stock_status_report(user_phone)
    
    # Fetch report WITH search for display
    stock_report = get_stock_status_report(user_phone, search_term=search) if search else full_stock_report
    alerts = [item for item in stock_report if item['status'] != 'HEALTHY']
    
    # Calculate total inward and outward across ALL items
    total_inward = 0
    total_outward = 0
    for item in full_stock_report:
        current_meters = item['current_meters']
        # Calculate inward/outward based on net position and transaction history
        # This requires summing from raw data - using current_meters to estimate
        if current_meters > 0:
            total_inward += current_meters
    
    # Get raw inward/outward from database for accurate totals
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                SUM(CASE WHEN transaction_type = 'INWARD' THEN meters ELSE 0 END) as total_inward,
                SUM(CASE WHEN transaction_type = 'OUTWARD' THEN meters ELSE 0 END) as total_outward,
                SUM(CASE WHEN transaction_type = 'INWARD' THEN meters ELSE -meters END) as net_meters,
                SUM(CASE WHEN transaction_type = 'INWARD' THEN thaans ELSE -thaans END) as net_thaans
            FROM inventory_ledger
            WHERE sender_phone = %s
        """, (user_phone,))
        result = cur.fetchone()
        total_inward = result[0] if result[0] else 0
        total_outward = result[1] if result[1] else 0
        net_meters = result[2] if result[2] else 0
        net_thaans = result[3] if result[3] else 0
    finally:
        cur.close()
        conn.close()
    
    stats = {
        "net_stock": round(net_meters, 2) if net_meters else 0,
        "total_inward": round(total_inward, 2) if total_inward else 0,
        "total_outward": round(total_outward, 2) if total_outward else 0,
        "total_thaans": net_thaans if net_thaans else 0
    }
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stock_report": stock_report,
        "profiles": stock_report,  # Added: This is what was missing for Live Stock by Profile!
        "alerts": alerts,
        "search_query": search or "",
        "stats": stats
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
async def show_inventory(request: Request):
    phone = request.cookies.get("auth_user")
    if not phone:
        return RedirectResponse(url="/login")

    # This is the line that was crashing
    items = get_inventory_details(sender_phone=phone)
    
    return templates.TemplateResponse("inventory.html", {
        "request": request, 
        "items": items
    })

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
