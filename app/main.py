from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
from app.web.dashboard import router as web_router
from app.api.auth import router as auth_router
from app.api.public_data import router as data_router

app = FastAPI(title="The Koshak Inventory")

# CORS is required once the frontend is hosted on a different domain (for example GitHub Pages).
allowed_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files (CSS/Images)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Mount your routers
app.include_router(web_router)                       # Now at api.thekoshak.com/
app.include_router(auth_router, prefix="/api")       # POST /api/auth/login  — token-based login
app.include_router(data_router, prefix="/api")       # GET  /api/data/stock|stats|ledger|export/csv

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.on_event("startup")
def startup_db():
    from app.services.db import setup_database
    setup_database()