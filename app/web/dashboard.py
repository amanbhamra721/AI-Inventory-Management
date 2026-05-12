from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from app.services.db import get_inventory_summary
from app.services.db import get_inventory_details

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def show_dashboard(request: Request, phone: str = None):
    """
    Main Dashboard view. 
    Usage: api.thekoshak.com/?phone=919876543210
    """
    # Fetch stats from DB
    # If no phone is passed, it shows global stats (you can change this for security)
    inventory_stats = get_inventory_summary(sender_phone=phone)
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "stats": inventory_stats,
            "phone": phone
        }
    )

@router.get("/inventory")
async def show_inventory(request: Request, phone: str = None):
    """
    Detailed inventory list view.
    """
    # Fetch the last 50 items for this specific customer
    items = get_inventory_details(sender_phone=phone)
    
    return templates.TemplateResponse(
        "inventory.html", 
        {
            "request": request, 
            "items": items,
            "phone": phone
        }
    )