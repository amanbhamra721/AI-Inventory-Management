# app/main.py
from fastapi import FastAPI
import uvicorn
from app.api.webhook import router as webhook_router

app = FastAPI(title="WhatsApp Inventory Webhook")

# Register the webhook endpoints
app.include_router(webhook_router)

if __name__ == "__main__":
    print("🚀 Starting FastAPI Server on http://localhost:5000")
    # Using app.main:app allows the server to auto-reload if you change code
    uvicorn.run("app.main:app", host="0.0.0.0", port=5000, reload=True)