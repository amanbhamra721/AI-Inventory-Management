import io
import csv
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.services.db import get_stock_status_report, get_inventory_details, get_db_connection
from app.services.jwt_auth import get_current_phone

router = APIRouter()


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
            "fabric":           row["fabric"],
            "shade_code":       row["shade_code"],
            "bale_no":          row["bale_no"],
            "brand_name":       row.get("brand_name"),
            "party_name":       row.get("party_name"),
            "reference_no":     row.get("reference_no"),
            "transaction_type": row["transaction_type"],
            "meters":           float(row["meters"] or 0),
            "thaans":           int(row["thaans"] or 0),
            "created_at":       row["created_at"].isoformat() if row.get("created_at") else None,
        })
    return result


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
