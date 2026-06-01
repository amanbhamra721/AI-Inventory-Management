import os
import threading
import time

from app.services.db import (
    get_document_retry_by_id,
    get_due_document_retries,
    insert_transaction,
    mark_document_retry_attempt,
    mark_document_retry_complete,
)
from app.services.document_router import process_document


def process_retry_item(item: dict):
    queue_id = item["id"]
    sender_phone = item["sender_phone"]
    image_path = item.get("image_path")

    if not image_path or not os.path.exists(image_path):
        mark_document_retry_attempt(queue_id, "Stored image path missing or file not found")
        return

    try:
        payload = process_document(image_path)
        if not payload:
            mark_document_retry_attempt(queue_id, "Parser could not extract valid payload")
            return

        success, message = insert_transaction(payload, sender_phone=sender_phone)
        if not success:
            mark_document_retry_attempt(queue_id, message)
            return

        mark_document_retry_complete(queue_id)
        try:
            os.remove(image_path)
        except Exception:
            pass
    except Exception as exc:
        mark_document_retry_attempt(queue_id, str(exc))


def process_due_document_retries(limit: int = 10):
    for item in get_due_document_retries(limit=limit):
        process_retry_item(item)


def retry_document_now(queue_id: int):
    item = get_document_retry_by_id(queue_id)
    if not item:
        return False, "Retry queue item not found"
    process_retry_item(item)
    refreshed = get_document_retry_by_id(queue_id)
    if not refreshed:
        return False, "Retry queue item disappeared unexpectedly"
    status = refreshed.get("status")
    if status == "COMPLETED":
        return True, "Retry completed successfully"
    if status == "FAILED_MANUAL_REVIEW":
        return False, refreshed.get("last_error") or "Retry attempts exhausted"
    return False, refreshed.get("last_error") or "Retry still pending"


def start_document_retry_worker(poll_seconds: int = 60, batch_limit: int = 10):
    """Start a daemon thread that periodically retries failed document images."""
    def _loop():
        while True:
            try:
                process_due_document_retries(limit=batch_limit)
            except Exception:
                pass
            time.sleep(poll_seconds)

    thread = threading.Thread(target=_loop, name="document-retry-worker", daemon=True)
    thread.start()
    return thread