import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.auth import verify_password
from app.services.db import get_db_connection
from app.services.jwt_auth import create_access_token

router = APIRouter()


class LoginRequest(BaseModel):
    phone: str
    password: str


@router.post("/auth/login")
def api_login(body: LoginRequest):
    """
    Token-based login for the static GitHub Pages frontend.
    Accepts phone + password, returns a signed JWT.
    The existing cookie-based /login route is untouched and still used by Oracle.
    """
    clean_phone = re.sub(r"\D", "", body.phone)
    if len(clean_phone) == 10:
        clean_phone = f"91{clean_phone}"

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT phone_number, hashed_password FROM users WHERE phone_number = %s AND is_active = true",
            (clean_phone,),
        )
        user = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid phone number or password.")

    token = create_access_token(clean_phone)
    return {"access_token": token, "token_type": "bearer", "phone": clean_phone}
