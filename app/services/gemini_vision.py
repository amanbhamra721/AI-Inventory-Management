import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from dotenv import load_dotenv

load_dotenv()


def _build_image_part(image_path: str):
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"

    with open(image_path, "rb") as image_file:
        image_b64 = base64.b64encode(image_file.read()).decode("utf-8")

    return {
        "inline_data": {
            "mime_type": mime_type,
            "data": image_b64,
        }
    }


def call_gemini(prompt: str, image_path: str | None = None):
    """Call Gemini generateContent API and return (text, error)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY is not set"

    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    parts = [{"text": prompt}]
    if image_path:
        try:
            parts.append(_build_image_part(image_path))
        except Exception as exc:
            return None, f"Image read error: {exc}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ]
    }

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
            candidates = body.get("candidates") or []
            if not candidates:
                return None, "No candidate response returned"

            parts_out = ((candidates[0].get("content") or {}).get("parts") or [])
            text_chunks = [part.get("text", "") for part in parts_out if isinstance(part, dict)]
            text = "\n".join([chunk for chunk in text_chunks if chunk]).strip()
            if not text:
                return None, "Empty text response from Gemini"
            return text, None
    except urllib.error.HTTPError as exc:
        try:
            err_text = exc.read().decode("utf-8")
        except Exception:
            err_text = str(exc)
        return None, f"Gemini HTTP error: {err_text}"
    except Exception as exc:
        return None, f"Gemini request failed: {exc}"


def extract_json(text: str):
    """Extract and parse first JSON object/array from Gemini text output."""
    if not text:
        return None

    stripped = text.strip()
    try:
        return json.loads(stripped)
    except Exception:
        pass

    patterns = [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            return json.loads(match.group(0))
        except Exception:
            continue

    return None
