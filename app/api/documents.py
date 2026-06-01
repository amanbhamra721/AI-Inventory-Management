import os
import tempfile
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services.db import (
    enqueue_document_retry,
    get_failed_document_retries,
    get_due_document_retries,
    get_product_catalog,
    insert_transaction,
    normalize_quality_name,
    upsert_product_catalog_entry,
)
from app.services.document_router import process_document, run_pipeline
from app.services.jwt_auth import get_current_phone

router = APIRouter()
PERSISTENT_IMAGE_DIR = os.path.join("app", "storage", "pending_documents")


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
    persistent_path = None

    try:
        os.makedirs(PERSISTENT_IMAGE_DIR, exist_ok=True)
        image_bytes = await image.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(image_bytes)
            temp_path = temp_file.name

        persistent_filename = f"{phone}_{int(os.path.getmtime(temp_path))}_{os.path.basename(image.filename)}"
        persistent_path = os.path.join(PERSISTENT_IMAGE_DIR, persistent_filename)
        shutil.copy2(temp_path, persistent_path)

        if transaction_type:
            doc_type = transaction_type.strip().upper()
            if doc_type not in {"INWARD", "OUTWARD"}:
                raise HTTPException(status_code=400, detail="transaction_type must be INWARD or OUTWARD")
            payload = run_pipeline(temp_path, doc_type)
        else:
            payload = process_document(temp_path)

        if not payload:
            queue_id = enqueue_document_retry(
                sender_phone=phone,
                image_path=persistent_path,
                reason="PARSER_RETURNED_NO_PAYLOAD",
                payload={"transaction_type": transaction_type},
            )
            raise HTTPException(status_code=422, detail="Could not extract valid structured data from document")

        success, message = insert_transaction(payload, sender_phone=phone)
        if not success:
            enqueue_document_retry(
                sender_phone=phone,
                image_path=persistent_path,
                reason=message,
                payload=payload,
            )
            raise HTTPException(status_code=400, detail=message)

        if persistent_path and os.path.exists(persistent_path):
            os.remove(persistent_path)

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


@router.get("/documents/retries/pending")
def api_pending_retries(phone: str = Depends(get_current_phone)):
    rows = get_due_document_retries(limit=50)
    return [
        {
            "id": row.get("id"),
            "sender_phone": row.get("sender_phone"),
            "image_path": row.get("image_path"),
            "reason": row.get("reason"),
            "retry_count": row.get("retry_count"),
            "max_retry_count": row.get("max_retry_count"),
            "next_retry_at": row.get("next_retry_at").isoformat() if row.get("next_retry_at") else None,
            "status": row.get("status"),
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        }
        for row in rows
        if row.get("sender_phone") == phone
    ]


@router.get("/documents/retries/failed")
def api_failed_retries(phone: str = Depends(get_current_phone)):
    rows = get_failed_document_retries(sender_phone=phone, limit=50)
    return [
        {
            "id": row.get("id"),
            "sender_phone": row.get("sender_phone"),
            "image_path": row.get("image_path"),
            "reason": row.get("reason"),
            "last_error": row.get("last_error"),
            "retry_count": row.get("retry_count"),
            "max_retry_count": row.get("max_retry_count"),
            "status": row.get("status"),
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        }
        for row in rows
    ]
