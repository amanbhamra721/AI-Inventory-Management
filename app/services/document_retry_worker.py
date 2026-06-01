import os
import threading
import time

from app.services.db import (
    get_due_document_retries,
    insert_transaction,
    mark_document_retry_attempt,
    mark_document_retry_complete,
)
from app.services.document_router import process_document


def _process_retry_item(item: dict):
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
        _process_retry_item(item)


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