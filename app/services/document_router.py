# app/services/document_router.py
import time
import json
from app.services.gemini_vision import call_gemini, extract_json
from app.utils.validators import validate_inward, validate_outward

def classify_document(image_path):
    print("\n[Step 0] Analyzing Document Type...")
    prompt = """
    Look at this image and determine the document type based on these keywords:
    1. If it is printed and contains "BR COTTFAB", "MAHARASHTRA", or "Bale No", reply strictly with the word: INWARD
    2. If it is handwritten and contains "VCM", "ORDER / ESTIMATE FORM", or handwritten math, reply strictly with the word: OUTWARD
    
    Reply with NOTHING ELSE but the single word INWARD or OUTWARD.
    """
    
    result, error = call_gemini(prompt, image_path)
    
    # --- DEBUGGING ADDITION ---
    if error:
        print(f"❌ Step 0 API Error: {error}")
        return "UNKNOWN"
    
    print(f"DEBUG: Raw Classification Result: '{result.strip()}'")
    # --------------------------

    clean_result = result.strip().upper()
    if "INWARD" in clean_result: return "INWARD"
    if "OUTWARD" in clean_result: return "OUTWARD"
    
    return "UNKNOWN"

def run_pipeline(image_path, doc_type, attempt=1, max_retries=3, retry_hint=None):
    print(f"\n{'='*50}\n⚙️ [Attempt {attempt}] Processing as {doc_type}\n{'='*50}")
    
    if doc_type == "INWARD":
        ocr_prompt = """
        ACT AS: High-precision OCR Engine. Transcribe this INWARD printed table.
        
        HEADER EXTRACTION RULES:
        1. Look at the top right header area.
        2. Extract 'Bale No' (e.g., BR22633).
        3. Extract 'Date' (e.g., 28/01/2025).
        4. Extract 'Fold' (e.g., 100).
        5. Extract 'Width' (e.g., 42").
        TABLE RULES:
        1. Flatten into a single vertical list. Transcribe all items from the LEFT column (Sr 1-15) then RIGHT column (Sr 16-21).
        2. Must be exactly 21 lines, strictly numbered 1 to 21. Output plain text only.
        """
        json_prompt = """
        CRITICAL EXTRACTION & MATH RULES:
        1. EXACT TRANSCRIPTION: For the `summary` block (`total_meters`, `total_thaans`), you MUST extract the exact printed numbers from the bottom of the document. Do NOT calculate these totals yourself. Read them exactly as they are written on the page.
        2. OCR VERIFICATION: Pay extreme attention to similar-looking digits (e.g., 4 vs 5, 3 vs 8) especially near decimal points.
        3. FORCED RECONCILIATION: Before returning the JSON, silently sum the `meters` from all your extracted `items`. Compare your sum to the printed `total_meters`. If they do not match, YOU HAVE MADE AN OCR ERROR. Re-read the line items and correct your mistake before generating the final JSON. The printed total on the page is the Absolute Source of Truth.

        Convert OCR to strict JSON. Map to this structure:
        {
        "transaction_type": "INWARD", 
        "metadata": {
            "bale_no": string, 
            "date": string, 
            "fold": string, 
            "width": string
        },
        "summary": {"total_thaans": float, "total_meters": float}, 
        "items": [{"sr_no": int, "fabric": string, "thaans": float, "meters": float, "shade_code": string}]
        }
        """
        validator = validate_inward
        
    elif doc_type == "OUTWARD":
        ocr_prompt = """
        ACT AS: High-precision OCR Engine. Transcribe this OUTWARD handwritten estimate.
        
        HEADER EXTRACTION RULES:
        1. Look at the top left/center. Extract the 'No.' (e.g., 1352).
        2. Look at the top right 'Dated' field. Extract the date (e.g., 4/10).

        RULES:
        1. Transcribe the fabric names (e.g. F.V, Rubia).
        2. Extract the exact math equations written for each fabric (e.g., 48+34+59+47=476).
        3. CRITICAL: Look at the far right 'AMOUNT Rs.' column. Transcribe the specific price/amount listed for each individual fabric block.
        4. Extract the final grand totals and GST at the bottom. Output plain text only.
        """
        json_prompt = """
        Convert OCR to strict JSON. Convert fractions (1/2 to .5, 3/4 to .75).
        Make sure to map the individual line-item amounts to the 'price' key for each fabric.
        
        {
        "transaction_type": "OUTWARD", 
        "metadata": {
            "receipt_no": string, 
            "date": string
        },
        "summary": {"total_thaans": float, "total_meters": float, "grand_total_amount": float}, 
        "items": [{"fabric": string, "thaans": float, "meters": float, "price": float}]
        }
        """
        validator = validate_outward

    if retry_hint:
        ocr_prompt += f"\n🚨 PREVIOUS VALIDATION FAILED: {retry_hint}\nPlease re-scan and correct this specific error."

    # --- STEP 1: OCR ---
    print(f"[{doc_type} Step 1] Running Pure OCR Scan...")
    ocr_text, err = call_gemini(ocr_prompt, image_path)
    if err: 
        print(f"❌ OCR Failed: {err}")
        if attempt < max_retries and "timed out" in err: 
            return run_pipeline(image_path, doc_type, attempt + 1, max_retries, retry_hint)
        return None

    time.sleep(2)
    # --- STEP 2: JSON ---
    print(f"[{doc_type} Step 2] Structuring into JSON...")
    json_text, err = call_gemini(json_prompt + f"\n\nRAW OCR:\n{ocr_text}")
    data = extract_json(json_text) if json_text else None
    
    if not data: return None

    # --- STEP 3: VALIDATION ---
    is_valid, message = validator(data)
    
    if is_valid:
        print(f"✅ Success! {message}")
        return data
    elif attempt < max_retries:
        print(f"⚠️ Validation Failed: {message}")
        print("🔄 Self-Correction Triggered...")
        return run_pipeline(image_path, doc_type, attempt + 1, max_retries, retry_hint=message)
    else:
        print(f"🛑 Critical Failure after {max_retries} attempts: {message}")
        return None

def process_document(image_path):
    print(f"Starting pipeline for: {image_path}")
    doc_type = classify_document(image_path)
    if doc_type == "UNKNOWN":
        print("❌ Could not identify document type.")
        return None
    return run_pipeline(image_path, doc_type)