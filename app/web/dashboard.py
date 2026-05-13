from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.services.db import get_global_stats, get_stock_by_profile, get_inventory_details
from app.services.auth import verify_password
import re

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_current_user(request: Request):
    """Checks if the user has a valid session cookie."""
    user_phone = request.cookies.get("auth_user")
    if not user_phone:
        return None
    return user_phone


@router.get("/")
async def show_dashboard(request: Request, phone: str = None):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login") # Redirect to login if not authenticated

    # Fetch ERP data
    stats = get_global_stats(sender_phone=phone)
    profiles = get_stock_by_profile(sender_phone=phone)
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "stats": stats,
            "profiles": profiles,
            "phone": phone
        }
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