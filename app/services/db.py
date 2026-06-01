import json
import os
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")


def get_db_connection():
    """Connects to PostgreSQL using RealDictCursor for JSON-like row access."""
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)


def setup_database():
    """Creates base tables and applies non-breaking schema upgrades."""
    create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        phone_number VARCHAR(20) UNIQUE NOT NULL,
        hashed_password TEXT,
        full_name VARCHAR(100),
        role VARCHAR(20) DEFAULT 'ADMIN',
        business_type VARCHAR(50) DEFAULT 'TEXTILE',
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    create_receipts_table = """
    CREATE TABLE IF NOT EXISTS receipts (
        id SERIAL PRIMARY KEY,
        receipt_type VARCHAR(20),
        external_receipt_no VARCHAR(100),
        document_date VARCHAR(50),
        width VARCHAR(50),
        batch_no VARCHAR(100),
        fold VARCHAR(50),
        total_thaans NUMERIC,
        total_meters NUMERIC,
        grand_total_amount NUMERIC,
        sender_phone VARCHAR(20),
        image_url TEXT,
        notes TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    create_ledger_table = """
    CREATE TABLE IF NOT EXISTS inventory_ledger (
        id SERIAL PRIMARY KEY,
        sender_phone VARCHAR(20) NOT NULL,
        fabric VARCHAR(100) NOT NULL,
        shade_code VARCHAR(50),
        transaction_type VARCHAR(20) NOT NULL,
        meters NUMERIC(10, 2) DEFAULT 0,
        thaans INTEGER DEFAULT 0,
        bale_no VARCHAR(50),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    create_product_catalog_table = """
    CREATE TABLE IF NOT EXISTS product_catalog (
        id SERIAL PRIMARY KEY,
        sender_phone VARCHAR(20),
        canonical_name VARCHAR(150) NOT NULL,
        aliases TEXT[] DEFAULT '{}',
        brand_name VARCHAR(100),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(sender_phone, canonical_name)
    );
    """

    create_audit_table = """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY,
        action VARCHAR(100),
        table_name VARCHAR(50),
        record_id INTEGER,
        performed_by VARCHAR(20),
        details JSONB,
        timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    create_review_queue = """
    CREATE TABLE IF NOT EXISTS ai_review_queue (
        id SERIAL PRIMARY KEY,
        sender_phone VARCHAR(20),
        source_image VARCHAR(255),
        confidence_score NUMERIC(5,2) DEFAULT 0,
        reason TEXT,
        payload JSONB,
        status VARCHAR(20) DEFAULT 'PENDING',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TIMESTAMP WITH TIME ZONE,
        reviewed_by VARCHAR(20)
    );
    """

    create_edit_requests = """
    CREATE TABLE IF NOT EXISTS inventory_edit_requests (
        id SERIAL PRIMARY KEY,
        entry_id INTEGER NOT NULL,
        sender_phone VARCHAR(20) NOT NULL,
        requested_by VARCHAR(20) NOT NULL,
        reason TEXT NOT NULL,
        proposed_data JSONB NOT NULL,
        status VARCHAR(20) DEFAULT 'PENDING',
        approver_phone VARCHAR(20),
        approved_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    create_change_log = """
    CREATE TABLE IF NOT EXISTS inventory_change_logs (
        id SERIAL PRIMARY KEY,
        entry_id INTEGER NOT NULL,
        changed_by VARCHAR(20) NOT NULL,
        change_type VARCHAR(30) NOT NULL,
        old_data JSONB,
        new_data JSONB,
        reason TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    create_recon_sessions = """
    CREATE TABLE IF NOT EXISTS stock_reconciliation_sessions (
        id SERIAL PRIMARY KEY,
        sender_phone VARCHAR(20) NOT NULL,
        created_by VARCHAR(20) NOT NULL,
        status VARCHAR(20) DEFAULT 'OPEN',
        notes TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        closed_at TIMESTAMP WITH TIME ZONE
    );
    """

    create_recon_items = """
    CREATE TABLE IF NOT EXISTS stock_reconciliation_items (
        id SERIAL PRIMARY KEY,
        session_id INTEGER NOT NULL,
        fabric VARCHAR(100) NOT NULL,
        shade_code VARCHAR(50),
        system_meters NUMERIC(10,2) DEFAULT 0,
        physical_meters NUMERIC(10,2) DEFAULT 0,
        variance_meters NUMERIC(10,2) DEFAULT 0,
        reason_code VARCHAR(50),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(create_users_table)
        cur.execute(create_receipts_table)
        cur.execute(create_ledger_table)
        cur.execute(create_product_catalog_table)
        cur.execute(create_audit_table)
        cur.execute(create_review_queue)
        cur.execute(create_edit_requests)
        cur.execute(create_change_log)
        cur.execute(create_recon_sessions)
        cur.execute(create_recon_items)

        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS source VARCHAR(30) DEFAULT 'AI';")
        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS review_status VARCHAR(20) DEFAULT 'APPROVED';")
        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(5,2) DEFAULT 0;")
        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS unit_price NUMERIC(10,2) DEFAULT 0;")
        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS parent_entry_id INTEGER;")
        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS is_reversal BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE;")
        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS brand_name VARCHAR(100) DEFAULT 'BR';")
        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS party_name VARCHAR(255);")
        cur.execute("ALTER TABLE inventory_ledger ADD COLUMN IF NOT EXISTS reference_no VARCHAR(100);")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_ledger_sender_created ON inventory_ledger(sender_phone, created_at DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ledger_fabric_shade ON inventory_ledger(sender_phone, fabric, shade_code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ledger_brand_party ON inventory_ledger(sender_phone, brand_name, party_name);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_edit_requests_status ON inventory_edit_requests(sender_phone, status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_catalog_sender_canonical ON product_catalog(sender_phone, canonical_name);")
        conn.commit()
        print("✅ Database schema verified and upgraded.")
    except Exception as e:
        conn.rollback()
        print(f"❌ DB Setup Error: {e}")
    finally:
        cur.close()
        conn.close()


def log_audit(action: str, table_name: str, record_id: int, performed_by: str, details: dict | None = None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO audit_logs (action, table_name, record_id, performed_by, details)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (action, table_name, record_id, performed_by, json.dumps(details or {})),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def enqueue_ai_review(sender_phone: str, payload: dict, reason: str, confidence_score: float = 0.0, source_image: str | None = None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO ai_review_queue (sender_phone, source_image, confidence_score, reason, payload)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (sender_phone, source_image, confidence_score, reason, json.dumps(payload or {})),
        )
        queue_id = cur.fetchone()["id"]
        conn.commit()
        log_audit("QUEUE_REVIEW", "ai_review_queue", queue_id, sender_phone, {"reason": reason, "confidence": confidence_score})
        return queue_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def _is_duplicate_entry(cur, sender_phone: str, tx_type: str, fabric: str, shade_code: str, bale_no: str, meters: float, thaans: int):
    cur.execute(
        """
        SELECT id
        FROM inventory_ledger
        WHERE sender_phone = %s
          AND COALESCE(bale_no, '') = COALESCE(%s, '')
          AND transaction_type = %s
          AND fabric ILIKE %s
          AND COALESCE(shade_code, '') = COALESCE(%s, '')
          AND meters = %s
          AND thaans = %s
          AND is_deleted = FALSE
          AND created_at >= NOW() - INTERVAL '7 days'
        LIMIT 1
        """,
        (sender_phone, bale_no, tx_type, fabric, shade_code, meters, thaans),
    )
    return cur.fetchone() is not None


def _extract_confidence(data: dict) -> float:
    if "confidence_score" in data and data.get("confidence_score") is not None:
        return float(data.get("confidence_score"))
    scores = data.get("field_confidence", {}) or {}
    if isinstance(scores, dict) and scores:
        return round(min(float(v) for v in scores.values()), 2)
    # Validator-passing OCR without explicit confidence is treated as moderate-high confidence.
    return 0.90


def normalize_quality_name(extracted_name: str, sender_phone: str | None = None) -> str:
    """Resolve extracted quality names to a canonical product_catalog entry via aliases."""
    cleaned = (extracted_name or "").strip()
    if not cleaned:
        return "Unknown Fabric"

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT canonical_name
            FROM product_catalog
            WHERE is_active = TRUE
              AND (sender_phone = %s OR sender_phone IS NULL)
              AND (
                    LOWER(canonical_name) = LOWER(%s)
                    OR EXISTS (
                        SELECT 1
                        FROM unnest(COALESCE(aliases, ARRAY[]::TEXT[])) AS alias_name
                        WHERE LOWER(alias_name) = LOWER(%s)
                    )
              )
            ORDER BY sender_phone NULLS FIRST
            LIMIT 1
            """,
            (sender_phone, cleaned, cleaned),
        )
        row = cur.fetchone() or {}
        return (row.get("canonical_name") or cleaned).strip()
    except Exception:
        return cleaned
    finally:
        cur.close()
        conn.close()


def get_product_catalog(sender_phone: str, brand_name: str | None = None, query: str | None = None):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
    SELECT id, sender_phone, canonical_name, aliases, brand_name, is_active, created_at
    FROM product_catalog
    WHERE (sender_phone = %s OR sender_phone IS NULL) AND is_active = TRUE
    """
    params = [sender_phone]

    if brand_name:
        sql += " AND COALESCE(brand_name, '') ILIKE %s"
        params.append(f"%{brand_name}%")

    if query:
        sql += " AND (canonical_name ILIKE %s OR EXISTS (SELECT 1 FROM unnest(COALESCE(aliases, ARRAY[]::TEXT[])) AS a WHERE a ILIKE %s))"
        p = f"%{query}%"
        params.extend([p, p])

    sql += " ORDER BY canonical_name ASC"
    try:
        cur.execute(sql, tuple(params))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def upsert_product_catalog_entry(sender_phone: str, canonical_name: str, aliases: list[str] | None = None, brand_name: str | None = None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cleaned_name = (canonical_name or "").strip()
        if not cleaned_name:
            raise ValueError("canonical_name is required")

        cleaned_aliases = []
        for alias in aliases or []:
            a = (alias or "").strip()
            if a and a.lower() != cleaned_name.lower():
                cleaned_aliases.append(a)

        unique_aliases = list(dict.fromkeys(cleaned_aliases))

        cur.execute(
            """
            INSERT INTO product_catalog (sender_phone, canonical_name, aliases, brand_name, is_active)
            VALUES (%s, %s, %s, %s, TRUE)
            ON CONFLICT (sender_phone, canonical_name)
            DO UPDATE SET
                aliases = EXCLUDED.aliases,
                brand_name = EXCLUDED.brand_name,
                is_active = TRUE
            RETURNING id
            """,
            (sender_phone, cleaned_name, unique_aliases, brand_name),
        )
        row = cur.fetchone() or {}
        conn.commit()
        return row.get("id")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def insert_transaction(data, sender_phone="SYSTEM"):
    """
    Inserts AI transaction rows into inventory_ledger.
    Strict duplicate blocking and low-confidence review queue are enabled.
    Returns: (success: bool, message: str)
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        tx_type = (data.get("transaction_type") or "").upper()
        if tx_type not in {"INWARD", "OUTWARD"}:
            return False, "Unknown transaction type"

        metadata = data.get("metadata", {}) or {}
        summary = data.get("summary", {}) or {}
        items = data.get("items", []) or []
        if not items:
            return False, "No line items extracted"

        confidence = _extract_confidence(data)
        min_conf = float(os.getenv("MIN_AI_CONFIDENCE", "0.80"))
        if confidence < min_conf:
            queue_id = enqueue_ai_review(sender_phone, data, f"LOW_CONFIDENCE<{min_conf}", confidence)
            return False, f"Low confidence. Queued for review: {queue_id}"

        inserted_ids = []
        bale_no = metadata.get("bale_no") or metadata.get("receipt_no")
        reference_no = metadata.get("reference_no") or metadata.get("invoice_no") or metadata.get("challan_no") or bale_no
        brand_name = (metadata.get("brand_name") or "BR").strip()
        party_name = metadata.get("party_name")

        for item in items:
            raw_fabric = (item.get("fabric") or data.get("fabric") or "Unknown Fabric").strip()
            fabric = normalize_quality_name(raw_fabric, sender_phone)
            shade_code = (item.get("shade_code") or "").strip() or None
            meters = round(float(item.get("meters") or 0), 2)
            thaans = int(float(item.get("thaans") or 0))
            unit_price = float(item.get("price") or 0)

            if meters <= 0 and thaans <= 0:
                continue

            if _is_duplicate_entry(cur, sender_phone, tx_type, fabric, shade_code or "", bale_no or "", meters, thaans):
                conn.rollback()
                return False, f"Duplicate blocked for {fabric}/{shade_code or 'N/A'}"

            if tx_type == "OUTWARD":
                cur.execute(
                    """
                    SELECT COALESCE(SUM(CASE WHEN transaction_type='INWARD' THEN meters ELSE -meters END), 0) AS stock_meters
                    FROM inventory_ledger
                    WHERE sender_phone=%s AND fabric ILIKE %s AND COALESCE(shade_code, '') = COALESCE(%s, '')
                      AND is_deleted = FALSE
                    """,
                    (sender_phone, fabric, shade_code),
                )
                stock_meters = float((cur.fetchone() or {}).get("stock_meters") or 0)
                if stock_meters < meters:
                    conn.rollback()
                    return False, f"INSUFFICIENT STOCK for {fabric}. Available {stock_meters}m, requested {meters}m"

            cur.execute(
                """
                INSERT INTO inventory_ledger
                (sender_phone, fabric, shade_code, transaction_type, meters, thaans, bale_no, source, review_status, confidence_score, unit_price,
                 brand_name, party_name, reference_no)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'AI', 'APPROVED', %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (sender_phone, fabric, shade_code, tx_type, meters, thaans, bale_no, confidence, unit_price, brand_name, party_name, reference_no),
            )
            inserted_id = cur.fetchone()["id"]
            inserted_ids.append(inserted_id)
            log_audit("INSERT", "inventory_ledger", inserted_id, sender_phone, {"source": "AI"})

        if not inserted_ids:
            conn.rollback()
            return False, "No valid rows to insert"

        cur.execute(
            """
            INSERT INTO receipts (receipt_type, external_receipt_no, document_date, width, batch_no, fold, total_thaans, total_meters,
                                  grand_total_amount, sender_phone, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tx_type,
                metadata.get("reference_no") or metadata.get("receipt_no") or metadata.get("bale_no"),
                metadata.get("date"),
                metadata.get("width"),
                metadata.get("bale_no"),
                metadata.get("fold"),
                summary.get("total_thaans"),
                summary.get("total_meters"),
                summary.get("grand_total_amount"),
                sender_phone,
                f"Rows: {len(inserted_ids)}",
            ),
        )

        conn.commit()
        return True, f"Inserted {len(inserted_ids)} rows"
    except Exception as e:
        conn.rollback()
        return False, f"Database Transaction Error: {e}"
    finally:
        cur.close()
        conn.close()


def get_inventory_details(
    sender_phone: str,
    search_term: str | None = None,
    tx_type: str | None = None,
    brand_name: str | None = None,
    party_name: str | None = None,
):
    conn = get_db_connection()
    cur = conn.cursor()
    query = """
        SELECT id, fabric, shade_code, bale_no, transaction_type, meters, thaans, unit_price, source,
            brand_name, party_name, reference_no,
           review_status, confidence_score, created_at
    FROM inventory_ledger
    WHERE sender_phone = %s AND is_deleted = FALSE
    """
    params = [sender_phone]

    if search_term:
        query += " AND (fabric ILIKE %s OR shade_code ILIKE %s OR COALESCE(bale_no,'') ILIKE %s OR COALESCE(brand_name,'') ILIKE %s OR COALESCE(party_name,'') ILIKE %s OR COALESCE(reference_no,'') ILIKE %s)"
        p = f"%{search_term}%"
        params.extend([p, p, p, p, p, p])

    if brand_name:
        query += " AND COALESCE(brand_name, '') ILIKE %s"
        params.append(f"%{brand_name}%")

    if party_name:
        query += " AND COALESCE(party_name, '') ILIKE %s"
        params.append(f"%{party_name}%")

    if tx_type in {"INWARD", "OUTWARD"}:
        query += " AND transaction_type = %s"
        params.append(tx_type)

    query += " ORDER BY created_at DESC"

    try:
        cur.execute(query, tuple(params))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def get_stock_status_report(sender_phone: str, threshold_meters: float = 50.0, search_term: str | None = None):
    conn = get_db_connection()
    cur = conn.cursor()
    query = """
    SELECT
        fabric,
        shade_code,
        SUM(CASE WHEN transaction_type = 'INWARD' THEN meters ELSE -meters END) AS current_meters,
        SUM(CASE WHEN transaction_type = 'INWARD' THEN thaans ELSE -thaans END) AS current_thaans,
        SUM(CASE WHEN transaction_type = 'INWARD' THEN unit_price * meters ELSE 0 END) AS cost_valuation
    FROM inventory_ledger
    WHERE sender_phone = %s AND is_deleted = FALSE
    """
    params = [sender_phone]
    if search_term:
        query += " AND (fabric ILIKE %s OR shade_code ILIKE %s)"
        pattern = f"%{search_term}%"
        params.extend([pattern, pattern])

    query += " GROUP BY fabric, shade_code ORDER BY fabric ASC, shade_code ASC"

    try:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        report = []
        for row in rows:
            meters = float(row["current_meters"] or 0)
            status = "HEALTHY"
            if meters <= 0:
                status = "OUT_OF_STOCK"
            elif meters < threshold_meters:
                status = "LOW_STOCK"
            report.append({**row, "status": status})
        return report
    finally:
        cur.close()
        conn.close()


def get_recent_transactions(sender_phone: str, limit: int = 5):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, fabric, shade_code, transaction_type, meters, thaans, bale_no, created_at
            FROM inventory_ledger
            WHERE sender_phone=%s AND is_deleted=FALSE
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (sender_phone, limit),
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def get_dashboard_stats(sender_phone: str):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                SUM(CASE WHEN transaction_type='INWARD' THEN meters ELSE 0 END) AS total_inward,
                SUM(CASE WHEN transaction_type='OUTWARD' THEN meters ELSE 0 END) AS total_outward,
                SUM(CASE WHEN transaction_type='INWARD' THEN meters ELSE -meters END) AS net_meters,
                SUM(CASE WHEN transaction_type='INWARD' THEN thaans ELSE -thaans END) AS net_thaans,
                SUM(CASE WHEN transaction_type='INWARD' THEN unit_price * meters ELSE 0 END) AS capital_value
            FROM inventory_ledger
            WHERE sender_phone=%s AND is_deleted=FALSE
            """,
            (sender_phone,),
        )
        r = cur.fetchone() or {}
        return {
            "net_stock": round(float(r.get("net_meters") or 0), 2),
            "total_inward": round(float(r.get("total_inward") or 0), 2),
            "total_outward": round(float(r.get("total_outward") or 0), 2),
            "total_thaans": int(r.get("net_thaans") or 0),
            "total_capital_value": round(float(r.get("capital_value") or 0), 2),
        }
    finally:
        cur.close()
        conn.close()


def create_edit_request(entry_id: int, sender_phone: str, requested_by: str, reason: str, proposed_data: dict):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO inventory_edit_requests (entry_id, sender_phone, requested_by, reason, proposed_data)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (entry_id, sender_phone, requested_by, reason, json.dumps(proposed_data or {})),
        )
        req_id = cur.fetchone()["id"]
        conn.commit()
        log_audit("EDIT_REQUESTED", "inventory_edit_requests", req_id, requested_by, {"entry_id": entry_id})
        return req_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def _insert_reversal_and_corrected(cur, entry: dict, new_data: dict, approver_phone: str, reason: str):
    original_type = entry["transaction_type"]
    reverse_type = "OUTWARD" if original_type == "INWARD" else "INWARD"

    cur.execute(
        """
        INSERT INTO inventory_ledger
        (sender_phone, fabric, shade_code, transaction_type, meters, thaans, bale_no, source, review_status,
         confidence_score, unit_price, parent_entry_id, is_reversal)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'MANUAL_EDIT', 'APPROVED', 1.00, %s, %s, TRUE)
        RETURNING id
        """,
        (
            entry["sender_phone"],
            entry["fabric"],
            entry.get("shade_code"),
            reverse_type,
            float(entry.get("meters") or 0),
            int(entry.get("thaans") or 0),
            entry.get("bale_no"),
            float(entry.get("unit_price") or 0),
            entry["id"],
        ),
    )
    reversal_id = cur.fetchone()["id"]

    corrected = {
        "fabric": new_data.get("fabric", entry.get("fabric")),
        "shade_code": new_data.get("shade_code", entry.get("shade_code")),
        "bale_no": new_data.get("bale_no", entry.get("bale_no")),
        "transaction_type": new_data.get("transaction_type", entry.get("transaction_type")),
        "meters": float(new_data.get("meters", entry.get("meters") or 0)),
        "thaans": int(float(new_data.get("thaans", entry.get("thaans") or 0))),
        "unit_price": float(new_data.get("unit_price", entry.get("unit_price") or 0)),
    }

    cur.execute(
        """
        INSERT INTO inventory_ledger
        (sender_phone, fabric, shade_code, transaction_type, meters, thaans, bale_no, source, review_status,
         confidence_score, unit_price, parent_entry_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'MANUAL_EDIT', 'APPROVED', 1.00, %s, %s)
        RETURNING id
        """,
        (
            entry["sender_phone"],
            corrected["fabric"],
            corrected["shade_code"],
            corrected["transaction_type"],
            corrected["meters"],
            corrected["thaans"],
            corrected["bale_no"],
            corrected["unit_price"],
            entry["id"],
        ),
    )
    corrected_id = cur.fetchone()["id"]

    cur.execute("UPDATE inventory_ledger SET is_deleted=TRUE, updated_at=NOW() WHERE id=%s", (entry["id"],))
    cur.execute(
        """
        INSERT INTO inventory_change_logs (entry_id, changed_by, change_type, old_data, new_data, reason)
        VALUES (%s, %s, 'REVERSAL_CORRECTION', %s, %s, %s)
        """,
        (entry["id"], approver_phone, json.dumps(entry), json.dumps(corrected), reason),
    )
    return reversal_id, corrected_id


def approve_edit_request(request_id: int, approver_phone: str):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM inventory_edit_requests WHERE id=%s AND status='PENDING'", (request_id,))
        req = cur.fetchone()
        if not req:
            return False, "Request not found or already processed"

        cur.execute("SELECT * FROM inventory_ledger WHERE id=%s AND is_deleted=FALSE", (req["entry_id"],))
        entry = cur.fetchone()
        if not entry:
            return False, "Original entry not found"

        proposed = req.get("proposed_data") or {}
        if isinstance(proposed, str):
            proposed = json.loads(proposed)

        quantity_or_financial_change = any(
            k in proposed for k in ["meters", "thaans", "unit_price", "transaction_type"]
        )

        if quantity_or_financial_change:
            _insert_reversal_and_corrected(cur, entry, proposed, approver_phone, req["reason"])
        else:
            updated = {
                "fabric": proposed.get("fabric", entry.get("fabric")),
                "shade_code": proposed.get("shade_code", entry.get("shade_code")),
                "bale_no": proposed.get("bale_no", entry.get("bale_no")),
            }
            cur.execute(
                """
                UPDATE inventory_ledger
                SET fabric=%s, shade_code=%s, bale_no=%s, updated_at=NOW()
                WHERE id=%s
                """,
                (updated["fabric"], updated["shade_code"], updated["bale_no"], entry["id"]),
            )
            cur.execute(
                """
                INSERT INTO inventory_change_logs (entry_id, changed_by, change_type, old_data, new_data, reason)
                VALUES (%s, %s, 'DIRECT_UPDATE', %s, %s, %s)
                """,
                (entry["id"], approver_phone, json.dumps(entry), json.dumps(updated), req["reason"]),
            )

        cur.execute(
            """
            UPDATE inventory_edit_requests
            SET status='APPROVED', approver_phone=%s, approved_at=NOW()
            WHERE id=%s
            """,
            (approver_phone, request_id),
        )

        conn.commit()
        log_audit("EDIT_APPROVED", "inventory_edit_requests", request_id, approver_phone, {"entry_id": req["entry_id"]})
        return True, "Edit approved and applied"
    except Exception as e:
        conn.rollback()
        return False, f"Approval failed: {e}"
    finally:
        cur.close()
        conn.close()


def reject_edit_request(request_id: int, approver_phone: str, reason: str = ""):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE inventory_edit_requests
            SET status='REJECTED', approver_phone=%s, approved_at=NOW(), reason = CONCAT(reason, %s)
            WHERE id=%s AND status='PENDING'
            """,
            (approver_phone, f" | Rejection: {reason}" if reason else "", request_id),
        )
        changed = cur.rowcount
        conn.commit()
        if changed:
            log_audit("EDIT_REJECTED", "inventory_edit_requests", request_id, approver_phone, {"reason": reason})
        return changed > 0
    except Exception:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def get_pending_edit_requests(sender_phone: str, limit: int = 20):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT r.*, l.fabric, l.shade_code, l.bale_no, l.transaction_type, l.meters, l.thaans
            FROM inventory_edit_requests r
            JOIN inventory_ledger l ON l.id = r.entry_id
            WHERE r.sender_phone=%s AND r.status='PENDING'
            ORDER BY r.created_at DESC
            LIMIT %s
            """,
            (sender_phone, limit),
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def create_stock_adjustment(sender_phone: str, created_by: str, fabric: str, shade_code: str | None, bale_no: str | None,
                            meters_delta: float, thaans_delta: int, reason_code: str, unit_price: float = 0.0):
    if meters_delta == 0 and thaans_delta == 0:
        return False, "No variance to adjust"

    sign = 1 if meters_delta >= 0 else -1
    if thaans_delta != 0 and ((thaans_delta > 0 and sign < 0) or (thaans_delta < 0 and sign > 0)):
        return False, "Meters and thaans deltas must have same direction"

    tx_type = "INWARD" if sign > 0 else "OUTWARD"
    meters = abs(round(float(meters_delta), 2))
    thaans = abs(int(thaans_delta))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO inventory_ledger
            (sender_phone, fabric, shade_code, transaction_type, meters, thaans, bale_no, source, review_status,
             confidence_score, unit_price)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'ADJUSTMENT', 'APPROVED', 1.00, %s)
            RETURNING id
            """,
            (sender_phone, fabric, shade_code, tx_type, meters, thaans, bale_no, unit_price),
        )
        entry_id = cur.fetchone()["id"]
        conn.commit()
        log_audit("STOCK_ADJUSTMENT", "inventory_ledger", entry_id, created_by, {"reason_code": reason_code})
        return True, f"Adjustment recorded with entry {entry_id}"
    except Exception as e:
        conn.rollback()
        return False, f"Adjustment failed: {e}"
    finally:
        cur.close()
        conn.close()


def create_reconciliation_session(sender_phone: str, created_by: str, notes: str | None = None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO stock_reconciliation_sessions (sender_phone, created_by, notes)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (sender_phone, created_by, notes),
        )
        session_id = cur.fetchone()["id"]
        conn.commit()
        return session_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def add_reconciliation_item(session_id: int, fabric: str, shade_code: str | None, system_meters: float,
                            physical_meters: float, reason_code: str | None = None):
    variance = round(float(physical_meters) - float(system_meters), 2)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO stock_reconciliation_items
            (session_id, fabric, shade_code, system_meters, physical_meters, variance_meters, reason_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (session_id, fabric, shade_code, system_meters, physical_meters, variance, reason_code),
        )
        rec_id = cur.fetchone()["id"]
        conn.commit()
        return rec_id, variance
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def close_reconciliation_session(session_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE stock_reconciliation_sessions
            SET status='CLOSED', closed_at=NOW()
            WHERE id=%s AND status='OPEN'
            """,
            (session_id,),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def direct_update_inventory_entry(entry_id: int, sender_phone: str, changed_by: str, payload: dict):
    """Directly updates a ledger entry and writes an audit/change-log record."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT * FROM inventory_ledger
            WHERE id=%s AND sender_phone=%s AND is_deleted=FALSE
            """,
            (entry_id, sender_phone),
        )
        old_row = cur.fetchone()
        if not old_row:
            return False, "Entry not found"

        updated = {
            "fabric": payload.get("fabric", old_row.get("fabric")),
            "shade_code": payload.get("shade_code", old_row.get("shade_code")),
            "bale_no": payload.get("bale_no", old_row.get("bale_no")),
            "transaction_type": payload.get("transaction_type", old_row.get("transaction_type")),
            "meters": float(payload.get("meters", old_row.get("meters") or 0)),
            "thaans": int(float(payload.get("thaans", old_row.get("thaans") or 0)),),
            "unit_price": float(payload.get("unit_price", old_row.get("unit_price") or 0)),
        }

        if updated["meters"] < 0 or updated["thaans"] < 0:
            return False, "Meters and thaans must be non-negative"

        cur.execute(
            """
            UPDATE inventory_ledger
            SET fabric=%s,
                shade_code=%s,
                bale_no=%s,
                transaction_type=%s,
                meters=%s,
                thaans=%s,
                unit_price=%s,
                source='MANUAL_EDIT',
                updated_at=NOW()
            WHERE id=%s AND sender_phone=%s
            """,
            (
                updated["fabric"],
                updated["shade_code"],
                updated["bale_no"],
                updated["transaction_type"],
                updated["meters"],
                updated["thaans"],
                updated["unit_price"],
                entry_id,
                sender_phone,
            ),
        )

        cur.execute(
            """
            INSERT INTO inventory_change_logs (entry_id, changed_by, change_type, old_data, new_data, reason)
            VALUES (%s, %s, 'DIRECT_UPDATE', %s, %s, %s)
            """,
            (entry_id, changed_by, json.dumps(old_row), json.dumps(updated), "Direct edit"),
        )
        conn.commit()
        log_audit("DIRECT_EDIT", "inventory_ledger", entry_id, changed_by, {"entry_id": entry_id})
        return True, "Entry updated"
    except Exception as e:
        conn.rollback()
        return False, f"Update failed: {e}"
    finally:
        cur.close()
        conn.close()


def get_activity_logs(sender_phone: str, limit: int = 25):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT a.*
            FROM audit_logs a
            WHERE a.performed_by = %s OR a.record_id IN (
                SELECT id FROM inventory_ledger WHERE sender_phone = %s
            )
            ORDER BY a.timestamp DESC
            LIMIT %s
            """,
            (sender_phone, sender_phone, limit),
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def get_fast_slow_moving(sender_phone: str, days: int = 30):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT fabric, shade_code,
                   COUNT(*) FILTER (WHERE transaction_type='OUTWARD') AS outward_moves,
                   SUM(CASE WHEN transaction_type='OUTWARD' THEN meters ELSE 0 END) AS outward_meters
            FROM inventory_ledger
            WHERE sender_phone=%s AND is_deleted=FALSE AND created_at >= NOW() - (%s || ' days')::interval
            GROUP BY fabric, shade_code
            ORDER BY outward_meters DESC NULLS LAST
            """,
            (sender_phone, days),
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def get_aging_report(sender_phone: str):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                fabric,
                shade_code,
                COALESCE(SUM(CASE WHEN transaction_type='INWARD' THEN meters ELSE -meters END), 0) AS current_meters,
                MAX(created_at) AS last_movement_at,
                DATE_PART('day', NOW() - MAX(created_at))::INT AS days_since_movement
            FROM inventory_ledger
            WHERE sender_phone=%s AND is_deleted=FALSE
            GROUP BY fabric, shade_code
            HAVING COALESCE(SUM(CASE WHEN transaction_type='INWARD' THEN meters ELSE -meters END), 0) > 0
            ORDER BY days_since_movement DESC
            """,
            (sender_phone,),
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def get_global_stats(sender_phone: str = None):
    """Compatibility helper retained for existing imports."""
    if not sender_phone:
        return {"total_inward": 0, "total_outward": 0, "net_stock": 0}
    stats = get_dashboard_stats(sender_phone)
    return {
        "total_inward": stats["total_inward"],
        "total_outward": stats["total_outward"],
        "net_stock": stats["net_stock"],
    }


def get_stock_by_profile(sender_phone: str = None):
    """Compatibility helper retained for existing imports."""
    if not sender_phone:
        return []
    report = get_stock_status_report(sender_phone)
    shaped = []
    for row in report:
        shaped.append(
            {
                "cloth_name": row.get("fabric"),
                "shade_number": row.get("shade_code"),
                "width": None,
                "fabric_type": None,
                "available_qty": row.get("current_meters"),
                "cost_valuation": row.get("cost_valuation"),
            }
        )
    return shaped