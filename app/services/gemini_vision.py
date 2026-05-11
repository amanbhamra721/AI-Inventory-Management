# app/services/gemini_vision.py
import os
import json
import base64
import requests
import re
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

def extract_json(text):
    """Robustly extracts JSON from a string."""
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match: return json.loads(match.group())
        return None
    except Exception:
        return None

def call_gemini(prompt, image_path=None):
    """A single, reusable function to call the Gemini 2.5 Flash API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={API_KEY}"
    
    parts = [{"text": prompt}]
    
    if image_path:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        parts.append({
            "inline_data": {"mime_type": "image/jpeg", "data": image_data}
        })
        
    payload = {"contents": [{"parts": parts}]}
    
    try:
        response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=60)
        if response.status_code != 200: 
            return None, f"API Error {response.status_code}: {response.text}"
        return response.json()['candidates'][0]['content']['parts'][0]['text'], None
    except requests.exceptions.Timeout:
        return None, "Request timed out."
    except Exception as e:
        return None, str(e)