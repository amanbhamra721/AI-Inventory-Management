import json
import time
from app.services.gemini_vision import call_gemini, extract_json
from app.utils.validators import validate_inward, validate_outward


def classify_document(image_path):
    print("\n[Step 0] Analyzing Document Type...")
    # Shifted from hardcoded keywords to semantic intent.
    prompt = """
    Look at this image and determine if it is an INWARD (purchase/supplier) or OUTWARD (sale/estimate) document.

    INWARD indicators: Words like "Packing Slip", "Mfg. Co.", "Mills", "Dyeing", or supplier headers (e.g., Prakash, Nitin, Padamshree).
    OUTWARD indicators: Words like "Estimate", "Bill", "To:", or sales to specific buyers (e.g., Bombay Rubia House).

    Reply with NOTHING ELSE but the single word INWARD or OUTWARD.
    """

    result, error = call_gemini(prompt, image_path)

    if error:
        print(f"❌ Step 0 API Error: {error}")
        return "UNKNOWN"

    clean_result = result.strip().upper()
    if "INWARD" in clean_result:
        return "INWARD"
    if "OUTWARD" in clean_result:
        return "OUTWARD"

    return "UNKNOWN"


def _repair_failed_payload(doc_type: str, ocr_text: str, failed_data: dict, validation_message: str):
    """One final correction pass that repairs JSON against validator feedback."""
    repair_prompt = f"""
    You are repairing a previously extracted {doc_type} JSON payload for a textile receipt.
    The payload failed validation with this exact error:
    {validation_message}

    Rules:
    1. Keep the same JSON schema and return ONLY valid JSON.
    2. Preserve metadata if already correct.
    3. Fix ONLY line-item mapping and totals consistency issues.
    4. Items must include only true fabric rows; never include headers/totals.
    5. Ensure sum(items.meters) == summary.total_meters and sum(items.thaans) == summary.total_thaans.
    6. If uncertain for optional fields (shade/bale/price), use null or 0 for price.

    RAW OCR:
    {ocr_text}

    FAILED JSON:
    {json.dumps(failed_data, ensure_ascii=True)}
    """

    repaired_text, err = call_gemini(repair_prompt)
    if err:
        return None

    repaired_data = extract_json(repaired_text) if repaired_text else None
    if not repaired_data:
        return None

    return repaired_data


def _apply_minor_reconciliation(data: dict, meter_tolerance: float = 1.0, thaan_tolerance: float = 1.0):
    """Adjust small residual numeric drift by updating the last line item to match summary totals."""
    if not isinstance(data, dict):
        return data

    items = data.get("items") or []
    summary = data.get("summary") or {}
    if not items:
        return data

    try:
        target_meters = float(summary.get("total_meters") or 0)
        target_thaans = float(summary.get("total_thaans") or 0)
    except Exception:
        return data

    calc_meters = sum(float(item.get("meters") or 0) for item in items)
    calc_thaans = sum(float(item.get("thaans") or 0) for item in items)

    meter_diff = round(target_meters - calc_meters, 2)
    thaan_diff = round(target_thaans - calc_thaans, 2)

    if abs(meter_diff) > meter_tolerance or abs(thaan_diff) > thaan_tolerance:
        return data

    corrected = dict(data)
    corrected_items = [dict(item) for item in items]
    last_item = corrected_items[-1]

    last_item["meters"] = round(float(last_item.get("meters") or 0) + meter_diff, 2)
    last_item["thaans"] = round(float(last_item.get("thaans") or 0) + thaan_diff, 2)

    if float(last_item["meters"]) < 0 or float(last_item["thaans"]) < 0:
        return data

    corrected["items"] = corrected_items
    return corrected


def run_pipeline(image_path, doc_type, attempt=1, max_retries=3, retry_hint=None):
    print(f"\n{'=' * 50}\n⚙️ [Attempt {attempt}] Processing as {doc_type}\n{'=' * 50}")

    # Universal OCR prompt that adapts to any layout.
    ocr_prompt = f"""
    ACT AS: High-precision OCR Engine for a Wholesale Textile ERP.
    Transcribe this {doc_type} document accurately, preserving the relationship between quantities and fabric qualities.

    EXTRACTION RULES FOR ALL LAYOUTS (Handwritten or Printed):
    1. BRAND & PARTY: Identify the Supplier/Brand name (e.g., Prakash, Nitin, Padamshree) and the Buyer/Party name (e.g., Bombay Rubia House).
    2. REFERENCE ID: Find the primary document number (Bale No, Invoice No, Challan No).
    3. TABULAR DATA: Follow the rows carefully. Match the Quality/Fabric name with its respective Shade Codes, Thaans (pieces), and Meters.
    4. FRACTIONS: If handwritten fractions exist (1/4, 1/2, 3/4), transcribe them clearly.
    5. TOTALS: Capture the exact printed or written total meters and thaans at the bottom. Do NOT calculate them yourself.
    6. ROW INTEGRITY: Treat each data row as one line item. Do not merge two rows into one and do not split one row into multiple items.
    7. NO SUMMARY AS ITEM: Never include headers, footer totals, grand totals, narration, or remarks as a line item.
    8. NUMERIC CLARITY: Keep numbers exactly as printed; if uncertain, prefer null instead of guessing.

    Output a clean text representation of this data.
    """

    # Unified JSON schema mapping for the new database columns.
    json_prompt = """
    Convert the OCR text into strict JSON.

    CRITICAL MATH & DATA RULES:
    1. Convert all fractions to decimals (e.g., 1/4 = 0.25, 1/2 = 0.50, 3/4 = 0.75).
    2. SUM RECONCILIATION: Sum the `meters` from extracted items and match printed `total_meters`. If mismatch, re-check row mapping before output.
    3. THAAN RECONCILIATION: Sum the `thaans` from extracted items and match printed `total_thaans`. If mismatch, re-check row mapping before output.
    4. ITEM PURITY: Only actual fabric rows can appear inside `items`. Never include totals/header/narration rows as items.
    5. MISSING FIELDS: If barcode/shade/price/reference is absent, return null or 0 (for price), but do not invent values.
    6. OUTPUT ONLY JSON: Return a single strict JSON object with no prose or markdown.

    Use this exact JSON structure:
    {
        "transaction_type": "%s",
        "metadata": {
            "reference_no": "string (Extract Invoice, Challan, or Bale No)",
            "date": "string (DD/MM/YYYY)",
            "brand_name": "string (The Mill or Manufacturer)",
            "party_name": "string (The Buyer or Destination)"
        },
        "summary": {
            "total_thaans": float,
            "total_meters": float,
            "grand_total_amount": float (Set to 0 if not present)
        },
        "items": [
            {
                "fabric": "string (Quality Name)",
                "shade_code": "string",
                "bale_no": "string (If applicable per item)",
                "thaans": float,
                "meters": float,
                "price": float (Set to 0 if not present)
            }
        ]
    }
    """ % doc_type

    validator = validate_inward if doc_type == "INWARD" else validate_outward

    if retry_hint:
        ocr_prompt += f"\nPREVIOUS VALIDATION FAILED: {retry_hint}\nPlease re-scan and correct this specific error."
        json_prompt += f"\n\nPREVIOUS VALIDATION FAILED: {retry_hint}\nCorrect the extraction so JSON satisfies this validation."

    # Step 1: OCR
    print(f"[{doc_type} Step 1] Running Omni-OCR Scan...")
    ocr_text, err = call_gemini(ocr_prompt, image_path)
    if err:
        print(f"❌ OCR Failed: {err}")
        if attempt < max_retries and "timed out" in err.lower():
            return run_pipeline(image_path, doc_type, attempt + 1, max_retries, retry_hint)
        return None

    time.sleep(2)

    # Step 2: JSON
    print(f"[{doc_type} Step 2] Structuring into Standardized JSON...")
    json_text, err = call_gemini(json_prompt + f"\n\nRAW OCR:\n{ocr_text}")
    if err:
        print(f"❌ JSON Structuring Failed: {err}")
        if attempt < max_retries and "timed out" in err.lower():
            return run_pipeline(image_path, doc_type, attempt + 1, max_retries, retry_hint)
        return None

    data = extract_json(json_text) if json_text else None
    if not data:
        print("❌ Could not parse JSON payload from model response.")
        return None

    data = _apply_minor_reconciliation(data)

    # Step 3: Validation
    is_valid, message = validator(data)

    if is_valid:
        print(f"✅ Success! {message}")
        return data

    if attempt < max_retries:
        print(f"⚠️ Validation Failed: {message}")
        print("🔄 Self-Correction Triggered...")
        return run_pipeline(image_path, doc_type, attempt + 1, max_retries, retry_hint=message)

    repaired = _repair_failed_payload(doc_type, ocr_text, data, message)
    if repaired:
        repaired = _apply_minor_reconciliation(repaired)
        repaired_ok, repaired_message = validator(repaired)
        if repaired_ok:
            print(f"✅ Success after final repair pass! {repaired_message}")
            return repaired
        print(f"⚠️ Final repair pass still failed: {repaired_message}")

    print(f"🛑 Critical Failure after {max_retries} attempts: {message}")
    return None


def process_document(image_path):
    print(f"Starting pipeline for: {image_path}")
    doc_type = classify_document(image_path)
    if doc_type == "UNKNOWN":
        print("❌ Could not identify document type.")
        return None
    return run_pipeline(image_path, doc_type)
