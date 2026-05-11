from fastapi import APIRouter, Request, Response, BackgroundTasks
import os
import requests
from dotenv import load_dotenv

from app.services.document_router import process_document
from app.services.db import insert_transaction, setup_database

load_dotenv()
router = APIRouter()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

setup_database()

@router.get("/webhook")
async def verify_webhook(request: Request):
    # ... (Keep your existing GET logic exactly as is) ...
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(content="Token mismatch", status_code=403)


# ---------------------------------------------------------
# NEW: The Background Worker Function
# ---------------------------------------------------------
def process_image_task(media_id: str, sender_no: str):
    """This runs in the background so Meta doesn't time out."""
    print(f"\n⚙️ [BACKGROUND TASK] Starting pipeline for Media ID: {media_id}")
    try:
        # Let's verify the token actually exists in memory!
        if not WHATSAPP_TOKEN:
            print("🚨 FATAL ERROR: WHATSAPP_TOKEN is missing or None!")
            return

        header = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        response = requests.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=header)
        media_info = response.json()
        
        download_url = media_info.get("url")
        if not download_url:
            print(f"❌ Failed to get URL for {media_id}")
            # 🔥 THIS IS THE MAGIC LINE: Print Meta's exact error message
            print(f"🔍 META ERROR DETAILS: {media_info}") 
            return

        # ... rest of your download logic ...

        image_data = requests.get(download_url, headers=header).content
        temp_filename = f"incoming_{media_id}.jpg"
        
        with open(temp_filename, "wb") as f:
            f.write(image_data)
        
        # Run AI Pipeline
        result = process_document(temp_filename)
        
        if result:
            # 1. Save to Database
            insert_transaction(result)
            print(f"✅ Success! Data from {sender_no} saved. (Media ID: {media_id})")
            
            # 2. Extract data safely from the nested JSON
            doc_type = result.get("transaction_type", "UNKNOWN")
            
            # THE FIX: Looking for "items" instead of "line_items"
            items_array = result.get("items", [])
            items_processed = len(items_array) 
            
            # Drill down into the summary block
            summary = result.get("summary", {})
            total_thaans = summary.get("total_thaans", 0)
            total_meters = summary.get("total_meters", 0)
            grand_total = summary.get("grand_total_amount")
            
            # 3. Format the message
            icon = "🟢 INWARD" if doc_type == "INWARD" else "🔴 OUTWARD"
            
            reply_msg = (
                f"{icon} RECORDED\n"
                f"Rows Processed: {items_processed}\n"
                f"Total Thaans: {int(total_thaans)}\n"
                f"Total Meters: {total_meters} Meters\n"
            )
            
            # Add the financial total only if it's an Outward document
            if doc_type == "OUTWARD" and grand_total is not None:
                reply_msg += f"Grand Total: ₹{grand_total}\n"
                
            reply_msg += f"\nLogged successfully to inventory. ✅"
            
            # 4. Send the message!
            send_whatsapp_text(sender_no, reply_msg)
            
        else:
            # Send a failure message if the AI couldn't read it
            error_msg = "⚠️ Could not process this receipt. Please ensure the image is clear and try again."
            send_whatsapp_text(sender_no, error_msg)
            
        # Clean up
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

    except Exception as e:
        print(f"❌ Background Task Error: {e}")


# ---------------------------------------------------------
# UPDATED: The POST Route
# ---------------------------------------------------------
@router.post("/webhook")
async def receive_whatsapp_message(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        # Handle Status Updates
        if "statuses" in value:
            return {"status": "success"}

        messages = value.get("messages", [])
        if not messages:
            return {"status": "no_new_messages"}

        message = messages[0]
        sender_no = message.get("from")

        if message.get("type") == "image":
            media_id = message["image"]["id"]
            print(f"📥 Received Image webhook! Instantly acknowledging Meta...")
            
            # 🔥 Pass the heavy lifting to the background task!
            background_tasks.add_task(process_image_task, media_id, sender_no)

        return {"status": "success"} # 🔥 This hits Meta instantly, stopping the loop!

    except Exception as e:
        print(f"❌ Webhook Error: {e}")
        return {"status": "error"}
    
def send_whatsapp_text(to_number: str, text_message: str):
    """Sends a plain text message back to the WhatsApp user."""
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
    if response.status_code != 200:
        print(f"❌ Failed to send reply: {response.text}")