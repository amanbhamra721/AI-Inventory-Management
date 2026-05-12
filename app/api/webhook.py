from fastapi import APIRouter, Request, Response, BackgroundTasks
import os
import requests
import time
from dotenv import load_dotenv

from app.services.document_router import process_document
from app.services.db import insert_transaction, setup_database

load_dotenv()
router = APIRouter()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# Ensure DB is ready on startup
setup_database()

@router.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(content="Token mismatch", status_code=403)


# ---------------------------------------------------------
# BACKGROUND TASK: The "Heavy Lifting"
# ---------------------------------------------------------
def process_image_task(media_id: str, sender_no: str):
    """Handles image download, Gemini processing (with retries), and DB storage."""
    print(f"\n⚙️ [BACKGROUND TASK] Starting pipeline for Media ID: {media_id}")
    temp_filename = f"incoming_{media_id}.jpg"
    
    try:
        if not WHATSAPP_TOKEN:
            print("🚨 FATAL ERROR: WHATSAPP_TOKEN is missing!")
            return

        header = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        
        # 1. Get Image URL from Meta
        response = requests.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=header)
        media_info = response.json()
        
        download_url = media_info.get("url")
        if not download_url:
            print(f"❌ Failed to get URL for {media_id}. Details: {media_info}")
            return

        # 2. Download Image binary
        image_data = requests.get(download_url, headers=header).content
        with open(temp_filename, "wb") as f:
            f.write(image_data)
        
        # 3. AI Pipeline with Exponential Backoff (Fixes 503 Errors)
        result = None
        max_retries = 3
        delay = 2  # Start with 2 seconds

        for attempt in range(max_retries):
            try:
                print(f"[Step 0] Analyzing Document (Attempt {attempt + 1}/{max_retries})...")
                result = process_document(temp_filename)
                if result:
                    break  # Success!
            except Exception as e:
                # Check for Gemini 503 or 429
                if ("503" in str(e) or "UNAVAILABLE" in str(e)) and attempt < max_retries - 1:
                    print(f"⚠️ Gemini busy. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff: 2s, 4s, 8s
                    continue
                else:
                    print(f"❌ AI Pipeline failed: {e}")
                    break
        
        # 4. Handle Result and Database
        if result:
            insert_transaction(result)
            print(f"✅ Success! Data from {sender_no} saved.")

            # Data Extraction
            doc_type = result.get("transaction_type", "UNKNOWN")
            items_array = result.get("items", [])
            summary = result.get("summary", {})
            
            # Format Response
            icon = "🟢 INWARD" if doc_type == "INWARD" else "🔴 OUTWARD"
            reply_msg = (
                f"{icon} RECORDED\n"
                f"Rows: {len(items_array)}\n"
                f"Total Thaans: {int(summary.get('total_thaans', 0))}\n"
                f"Total Meters: {summary.get('total_meters', 0)}m\n"
            )
            
            if doc_type == "OUTWARD" and summary.get("grand_total_amount"):
                reply_msg += f"Grand Total: ₹{summary.get('grand_total_amount')}\n"
            
            reply_msg += "\nLogged successfully. ✅"
            send_whatsapp_text(sender_no, reply_msg)
            
        else:
            send_whatsapp_text(sender_no, "⚠️ Could not process image. Please try again later.")

    except Exception as e:
        print(f"❌ Background Task Error: {e}")
    finally:
        # 5. Clean up temporary file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)


# ---------------------------------------------------------
# WEBHOOK POST: Instant Acknowledgment
# ---------------------------------------------------------
@router.post("/webhook")
async def receive_whatsapp_message(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
        value = body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})

        # Ignore status updates (sent, delivered, read)
        if "statuses" in value:
            return {"status": "success"}

        messages = value.get("messages", [])
        if not messages:
            return {"status": "no_messages"}

        message = messages[0]
        sender_no = message.get("from")

        # Route images to the background task
        if message.get("type") == "image":
            media_id = message["image"]["id"]
            print(f"📥 Image received from {sender_no}. Passing to background...")
            background_tasks.add_task(process_image_task, media_id, sender_no)

        return {"status": "success"}  # Sent instantly to Meta

    except Exception as e:
        print(f"❌ Webhook Error: {e}")
        return {"status": "error"}

# ---------------------------------------------------------
# HELPER: Send Text Reply
# ---------------------------------------------------------
def send_whatsapp_text(to_number: str, text_message: str):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text_message}
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    # Fix for the 'to_phone_number' bug: Use 'to_number' variable
    print(f"DEBUG: Meta API Response for {to_number}: {response.status_code}")
    if response.status_code != 200:
        print(f"❌ Failed to send: {response.text}")