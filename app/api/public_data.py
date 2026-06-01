import io
import csv
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from app.services.db import get_stock_status_report, get_inventory_details, get_db_connection, direct_update_inventory_entry
from app.services.jwt_auth import get_current_phone

router = APIRouter()


class LedgerEditRequest(BaseModel):
    entry_id: int
    fabric: str
    shade_code: Optional[str] = None
    bale_no: Optional[str] = None
    transaction_type: str
    meters: float
    thaans: int
    unit_price: float = 0.0


@router.get("/data/stats")
def api_stats(phone: str = Depends(get_current_phone)):
    """Global stats for the top dashboard cards."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                SUM(CASE WHEN transaction_type = 'INWARD' THEN meters ELSE 0 END)  AS total_inward,
                SUM(CASE WHEN transaction_type = 'OUTWARD' THEN meters ELSE 0 END) AS total_outward,
                SUM(CASE WHEN transaction_type = 'INWARD' THEN meters ELSE -meters END) AS net_meters,
                SUM(CASE WHEN transaction_type = 'INWARD' THEN thaans ELSE -thaans END) AS net_thaans
            FROM inventory_ledger
            WHERE sender_phone = %s
            """,
            (phone,),
        )
        row = cur.fetchone() or {}
        return {
            "net_stock":     round(float(row.get("net_meters") or 0), 2),
            "total_inward":  round(float(row.get("total_inward") or 0), 2),
            "total_outward": round(float(row.get("total_outward") or 0), 2),
            "total_thaans":  int(row.get("net_thaans") or 0),
        }
    finally:
        cur.close()
        conn.close()


@router.get("/data/stock")
def api_stock(search: Optional[str] = None, phone: str = Depends(get_current_phone)):
    """Live stock report with optional search filter."""
    report = get_stock_status_report(phone, search_term=search)
    return report


@router.get("/data/ledger")
def api_ledger(
    search: Optional[str] = None,
    tx_type: Optional[str] = None,
    brand_name: Optional[str] = None,
    party_name: Optional[str] = None,
    phone: str = Depends(get_current_phone),
):
    """Full ledger history for the logged-in user."""
    rows = get_inventory_details(
        phone,
        search_term=search,
        tx_type=tx_type,
        brand_name=brand_name,
        party_name=party_name,
    )
    result = []
    for row in rows:
        result.append({
            "id":               row["id"],
            "fabric":           row["fabric"],
            "shade_code":       row["shade_code"],
            "bale_no":          row["bale_no"],
            "brand_name":       row.get("brand_name"),
            "party_name":       row.get("party_name"),
            "reference_no":     row.get("reference_no"),
            "transaction_type": row["transaction_type"],
            "meters":           float(row["meters"] or 0),
            "thaans":           int(row["thaans"] or 0),
            "unit_price":       float(row.get("unit_price") or 0),
            "created_at":       row["created_at"].isoformat() if row.get("created_at") else None,
        })
    return result


@router.post("/data/ledger/edit")
def api_ledger_edit(body: LedgerEditRequest, phone: str = Depends(get_current_phone)):
    tx_type = (body.transaction_type or "").upper()
    if tx_type not in {"INWARD", "OUTWARD"}:
        raise HTTPException(status_code=400, detail="transaction_type must be INWARD or OUTWARD")

    payload = {
        "fabric": body.fabric,
        "shade_code": body.shade_code,
        "bale_no": body.bale_no,
        "transaction_type": tx_type,
        "meters": body.meters,
        "thaans": body.thaans,
        "unit_price": body.unit_price,
    }
    ok, message = direct_update_inventory_entry(
        entry_id=body.entry_id,
        sender_phone=phone,
        changed_by=phone,
        payload=payload,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    return {"ok": True, "message": message}


@router.get("/data/export/csv")
def api_export_csv(phone: str = Depends(get_current_phone)):
    """Downloadable CSV of the live stock snapshot."""
    report = get_stock_status_report(phone)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Fabric", "Shade Code", "Current Meters", "Current Thaans", "Status"])
    for item in report:
        writer.writerow([
            item["fabric"],
            item["shade_code"],
            item["current_meters"],
            item["current_thaans"],
            item["status"].replace("_", " "),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=live_inventory_report.csv"},
    )
