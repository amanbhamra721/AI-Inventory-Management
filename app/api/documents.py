import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services.db import (
    get_product_catalog,
    insert_transaction,
    normalize_quality_name,
    upsert_product_catalog_entry,
)
from app.services.document_router import process_document, run_pipeline
from app.services.jwt_auth import get_current_phone

router = APIRouter()


class CatalogUpsertRequest(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=150)
    aliases: list[str] = Field(default_factory=list)
    brand_name: Optional[str] = Field(default=None, max_length=100)


@router.post("/documents/process")
async def api_process_document(
    image: UploadFile = File(...),
    transaction_type: Optional[str] = Form(None),
    phone: str = Depends(get_current_phone),
):
    """Run Omni-Parser on an uploaded slip and insert validated rows into inventory_ledger."""
    if not image.filename:
        raise HTTPException(status_code=400, detail="Image filename is required")

    suffix = os.path.splitext(image.filename)[1] or ".jpg"
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(await image.read())
            temp_path = temp_file.name

        if transaction_type:
            doc_type = transaction_type.strip().upper()
            if doc_type not in {"INWARD", "OUTWARD"}:
                raise HTTPException(status_code=400, detail="transaction_type must be INWARD or OUTWARD")
            payload = run_pipeline(temp_path, doc_type)
        else:
            payload = process_document(temp_path)

        if not payload:
            raise HTTPException(status_code=422, detail="Could not extract valid structured data from document")

        success, message = insert_transaction(payload, sender_phone=phone)
        if not success:
            raise HTTPException(status_code=400, detail=message)

        return {
            "ok": True,
            "message": message,
            "transaction_type": payload.get("transaction_type"),
            "metadata": payload.get("metadata", {}),
            "summary": payload.get("summary", {}),
            "items_count": len(payload.get("items", []) or []),
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@router.get("/catalog/products")
def api_catalog_products(
    brand_name: Optional[str] = None,
    q: Optional[str] = None,
    phone: str = Depends(get_current_phone),
):
    rows = get_product_catalog(sender_phone=phone, brand_name=brand_name, query=q)
    return [
        {
            "id": row.get("id"),
            "canonical_name": row.get("canonical_name"),
            "aliases": row.get("aliases") or [],
            "brand_name": row.get("brand_name"),
            "is_active": row.get("is_active"),
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        }
        for row in rows
    ]


@router.post("/catalog/products")
def api_upsert_catalog_product(body: CatalogUpsertRequest, phone: str = Depends(get_current_phone)):
    try:
        row_id = upsert_product_catalog_entry(
            sender_phone=phone,
            canonical_name=body.canonical_name,
            aliases=body.aliases,
            brand_name=body.brand_name,
        )
        return {"ok": True, "id": row_id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/catalog/normalize")
def api_normalize_name(name: str, phone: str = Depends(get_current_phone)):
    normalized = normalize_quality_name(name, sender_phone=phone)
    return {"input": name, "normalized": normalized}
