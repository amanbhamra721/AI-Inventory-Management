from fastapi import APIRouter, Request, Response, BackgroundTasks
import os
import requests
import time
import logging
from dotenv import load_dotenv

from app.services.document_router import process_document
from app.services.db import insert_transaction, setup_database

# ---------------------------------------------------------
# LOGGING CONFIGURATION (Forces immediate output)
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    handlers=[logging.StreamHandler()] # Ensures it prints straight to PM2
)
logger = logging.getLogger(__name__)

load_dotenv()
router = APIRouter()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# Ensure DB is ready on startup
setup_database()
logger.info("✅ Webhook router initialized and Database verified.")

@router.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        logger.info("✅ Meta Webhook Verification Successful")
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    logger.warning("⚠️ Webhook verification failed: Token mismatch")
    return Response(content="Token mismatch", status_code=403)


# ---------------------------------------------------------
# BACKGROUND TASK: The "Heavy Lifting"
# ---------------------------------------------------------
def process_image_task(media_id: str, sender_no: str):
    """Handles image download, Gemini processing (with retries), and DB storage."""
    logger.info(f"⚙️ [BACKGROUND TASK STARTED] Media ID: {media_id} | Sender: {sender_no}")
    temp_filename = f"incoming_{media_id}.jpg"
    
    try:
        if not WHATSAPP_TOKEN:
            logger.error("🚨 FATAL ERROR: WHATSAPP_TOKEN is missing in environment variables!")
            return

        header = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        
        # 1. Get Image URL from Meta
        logger.info("[Step 1] Fetching Image URL from Meta API...")
        url_response = requests.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=header)
        
        if url_response.status_code != 200:
            logger.error(f"❌ Meta API rejected URL request: {url_response.text}")
            return
            
        media_info = url_response.json()
        download_url = media_info.get("url")
        
        if not download_url:
            logger.error(f"❌ Failed to extract download URL. Meta Payload: {media_info}")
            return

        # 2. Download Image binary
        logger.info("[Step 2] Downloading Image Binary...")
        image_response = requests.get(download_url, headers=header)
        
        if image_response.status_code != 200:
            logger.error(f"❌ Failed to download image binary: {image_response.status_code}")
            return
            
        with open(temp_filename, "wb") as f:
            f.write(image_response.content)
        logger.info(f"✅ Image saved locally as {temp_filename}")
        
        # 3. AI Pipeline with Exponential Backoff
        result = None
        max_retries = 3
        delay = 2

        for attempt in range(max_retries):
            try:
                logger.info(f"[Step 3] Analyzing Document via AI (Attempt {attempt + 1}/{max_retries})...")
                result = process_document(temp_filename)
                if result:
                    logger.info("✅ AI Extraction Successful.")
                    break
            except Exception as e:
                if ("503" in str(e) or "UNAVAILABLE" in str(e)) and attempt < max_retries - 1:
                    logger.warning(f"⚠️ Gemini API busy. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= 2
                    continue
                else:
                    # logger.exception automatically prints the full traceback!
                    logger.exception("❌ AI Pipeline crashed during extraction:")
                    break
        
        # 4. Handle Result and Database
        if result:
            logger.info("[Step 4] Formatting data for Database Insertion...")
            
            # 1. Inject Sender Info
            result["sender_phone"] = sender_no 

            # 2. FABRIC MAPPING & NORMALIZATION
            # Define your master list here
            fabric_mapping = {
                "dhanlaxmi": "Dhanlaxmi full voile",
                "dhanlakshmi": "Dhanlaxmi full voile",
                "full voile": "Dhanlaxmi full voile"
            }

            raw_fabric = result.get("fabric", "").lower().strip()
            
            # Check if we have a professional name for what Gemini found
            if raw_fabric in fabric_mapping:
                result["fabric"] = fabric_mapping[raw_fabric]
            else:
                # Fallback: Just make it look clean (Capitalize first letter)
                result["fabric"] = raw_fabric.capitalize()
            
            # 3. Database Insertion
            try:
                insert_transaction(result)
                logger.info(f"✅ Success! Transaction from {sender_no} saved to DB.")
            except Exception as db_e:
                logger.exception("❌ DATABASE INSERTION CRASHED:")
                send_whatsapp_text(sender_no, "⚠️ System Error: Could not save receipt to the database.")
                return

            # --- Rest of your WhatsApp Reply logic stays the same ---
            doc_type = result.get("transaction_type", "UNKNOWN")
            items_array = result.get("items", [])
            summary = result.get("summary", {})
            
            icon = "🟢 INWARD" if doc_type == "INWARD" else "🔴 OUTWARD"
            reply_msg = (
                f"{icon} RECORDED\n"
                f"Fabric: {result['fabric']}\n" # Added this so the user sees the fixed name
                f"Rows: {len(items_array)}\n"
                f"Total Thaans: {int(summary.get('total_thaans', 0))}\n"
                f"Total Meters: {summary.get('total_meters', 0)}m\n"
            )
            
            if doc_type == "OUTWARD" and summary.get("grand_total_amount"):
                reply_msg += f"Grand Total: ₹{summary.get('grand_total_amount')}\n"
            
            reply_msg += "\nLogged successfully. ✅"
            
            logger.info("[Step 5] Sending confirmation back to user...")
            send_whatsapp_text(sender_no, reply_msg)
            
        else:
            logger.warning("⚠️ No valid result returned from AI. Sending failure message to user.")
            send_whatsapp_text(sender_no, "⚠️ Could not process image. Please ensure the image is clear and try again.")

    except Exception as e:
        logger.exception("❌ UNEXPECTED CRITICAL ERROR IN BACKGROUND TASK:")
    finally:
        # 5. Clean up temporary file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            logger.info("🗑️ Temporary image file cleaned up.")


# ---------------------------------------------------------
# WEBHOOK POST: Instant Acknowledgment
# ---------------------------------------------------------
@router.post("/webhook")
async def receive_whatsapp_message(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
        logger.info(f"📩 Webhook triggered. Processing payload...")
        
        value = body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})

        # Ignore status updates (sent, delivered, read)
        if "statuses" in value:
            logger.info("Status update received. Ignoring.")
            return {"status": "success"}

        messages = value.get("messages", [])
        if not messages:
            logger.info("No messages in payload.")
            return {"status": "no_messages"}

        message = messages[0]
        sender_no = message.get("from")

        # Route images to the background task
        if message.get("type") == "image":
            media_id = message["image"]["id"]
            logger.info(f"📸 Image payload detected from {sender_no}. Dispatching to background worker.")
            background_tasks.add_task(process_image_task, media_id, sender_no)
        else:
            logger.info(f"Received non-image message type: {message.get('type')}. Ignoring.")

        return {"status": "success"}  

    except Exception as e:
        logger.exception("❌ Error processing incoming Webhook POST:")
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
    
    if response.status_code == 200:
        logger.info(f"✅ WhatsApp reply successfully sent to {to_number}")
    else:
        logger.error(f"❌ Failed to send WhatsApp reply to {to_number}. Status: {response.status_code}, Response: {response.text}")