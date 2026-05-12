from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.webhook import router as whatsapp_router
from app.web.dashboard import router as web_router

app = FastAPI(title="The Koshak Inventory")

# Mount Static Files (CSS/Images)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Mount your routers
app.include_router(whatsapp_router, prefix="/api") # Now at api.thekoshak.com/api/webhook
app.include_router(web_router) # Now at api.thekoshak.com/

@app.on_event("startup")
def startup_db():
    from app.services.db import setup_database
    setup_database()