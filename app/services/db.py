# app/services/db.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables (Make sure your .env has DATABASE_URL)
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Establishes a connection to PostgreSQL using RealDictCursor for JSON-like row access."""
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

# ==========================================
# 1. SCHEMA SETUP (THE ERP FOUNDATION)
# ==========================================
def setup_database():
    """Creates the advanced relational tables for the ERP architecture."""
    
    create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        phone_number VARCHAR(20) UNIQUE NOT NULL,
        hashed_password TEXT,
        full_name VARCHAR(100),
        role VARCHAR(20) DEFAULT 'ADMIN', 
        business_type VARCHAR(50) DEFAULT 'TEXTILE', -- Preparing for segregation
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    create_profiles_table = """
    CREATE TABLE IF NOT EXISTS cloth_profiles (
        id SERIAL PRIMARY KEY,
        cloth_name VARCHAR(150) NOT NULL,
        color VARCHAR(50),
        shade_number VARCHAR(50),
        design_pattern VARCHAR(100),
        width VARCHAR(50),
        fabric_type VARCHAR(100),
        min_threshold NUMERIC DEFAULT 0,
        max_threshold NUMERIC DEFAULT 99999,
        base_price NUMERIC(10, 2),
        deleted_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(cloth_name, color, shade_number, design_pattern, width, fabric_type)
    );
    """

    create_receipts_table = """
    CREATE TABLE IF NOT EXISTS receipts (
        id SERIAL PRIMARY KEY,
        receipt_type VARCHAR(20), -- INWARD, OUTWARD, RETURN, WRITE_OFF
        external_receipt_no VARCHAR(100), -- Bale No or Invoice No
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
        shade_code VARCHAR(50) NOT NULL,
        transaction_type VARCHAR(20) NOT NULL, -- 'INWARD' or 'OUTWARD'
        meters NUMERIC(10, 2) DEFAULT 0,
        thaans INTEGER DEFAULT 0,
        bale_no VARCHAR(50),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    create_audit_table = """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY,
        action VARCHAR(100),
        table_name VARCHAR(50),
        record_id INTEGER,
        performed_by VARCHAR(20),
        timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(create_users_table)
        cursor.execute(create_profiles_table)
        cursor.execute(create_receipts_table)
        cursor.execute(create_ledger_table)
        cursor.execute(create_audit_table)
        conn.commit()
        print("✅ Advanced ERP PostgreSQL Schema Verified/Created.")
    except Exception as e:
        conn.rollback()
        print(f"❌ DB Setup Error: {e}")
    finally:
        cursor.close()
        conn.close()

# ==========================================
# 2. TRANSACTION ENGINE (CORE LOGIC)
# ==========================================
def get_or_create_cloth_profile(cursor, cloth_name, shade_number=None, width=None):
    """Looks up a cloth profile by name and attributes. Creates it if missing."""
    cursor.execute("""
        SELECT id FROM cloth_profiles 
        WHERE cloth_name ILIKE %s AND (shade_number = %s OR %s IS NULL)
    """, (f"%{cloth_name}%", shade_number, shade_number))
    
    result = cursor.fetchone()
    
    if result:
        return result['id']
    else:
        cursor.execute("""
            INSERT INTO cloth_profiles (cloth_name, shade_number, width)
            VALUES (%s, %s, %s) RETURNING id;
        """, (cloth_name, shade_number, width))
        return cursor.fetchone()['id']

def insert_transaction(data, sender_phone="SYSTEM"):
    """Processes receipts and safely updates the immutable inventory ledger."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        transaction_type = data.get('transaction_type')
        summary = data.get('summary', {})
        metadata = data.get('metadata', {})
        items = data.get('items', [])
        
        # 1. Create Master Receipt
        cursor.execute(
            """
            INSERT INTO receipts (
                receipt_type, external_receipt_no, document_date, 
                width, batch_no, fold, total_thaans, total_meters, 
                grand_total_amount, sender_phone
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (
                transaction_type,
                metadata.get('receipt_no') or metadata.get('bale_no'),
                metadata.get('date'),
                metadata.get('width'),
                metadata.get('bale_no'),
                metadata.get('fold'),
                summary.get('total_thaans'),
                summary.get('total_meters'),
                summary.get('grand_total_amount'),
                sender_phone
            )
        )
        receipt_id = cursor.fetchone()['id']
        
        # 2. Process Items into Ledger
        for item in items:
            fabric_name = item.get('fabric', 'Unknown Fabric')
            shade_code = item.get('shade_code')
            meters = float(item.get('meters', 0))
            price = item.get('price')
            
            profile_id = get_or_create_cloth_profile(cursor, fabric_name, shade_code, metadata.get('width'))
            
            if transaction_type == "INWARD":
                ledger_qty = meters 
                
            elif transaction_type == "OUTWARD":
                # Gatekeeper: Prevent Negative Stock
                cursor.execute("""
                    SELECT SUM(quantity) as current_stock 
                    FROM inventory_ledger 
                    WHERE cloth_profile_id = %s
                """, (profile_id,))
                
                stock_result = cursor.fetchone()
                current_stock = float(stock_result['current_stock'] or 0)
                
                if current_stock < meters:
                    raise ValueError(f"❌ INSUFFICIENT STOCK: Cannot dispatch {meters}m of '{fabric_name}'. Only {current_stock}m available.")
                
                ledger_qty = -meters 
            else:
                raise ValueError(f"Unknown transaction type: {transaction_type}")

            # Insert Ledger Row
            cursor.execute(
                """
                INSERT INTO inventory_ledger (
                    receipt_id, cloth_profile_id, movement_type, 
                    quantity, unit, price_per_unit, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                (receipt_id, profile_id, transaction_type, ledger_qty, 'Meters', price, sender_phone)
            )
            
        conn.commit()
        print(f"💾 Transaction {receipt_id} committed to Ledger successfully.")
        return True
        
    except ValueError as ve:
        conn.rollback()
        print(ve)
        return False
    except Exception as e:
        conn.rollback()
        print(f"❌ Database Transaction Error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# ==========================================
# 3. DASHBOARD ANALYTICS (REAL-TIME AGGREGATION)
# ==========================================
def get_global_stats(sender_phone: str = None):
    """Calculates high-level totals for the top dashboard cards."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
            SELECT 
                SUM(CASE WHEN movement_type = 'INWARD' THEN quantity ELSE 0 END) as total_inward,
                SUM(CASE WHEN movement_type = 'OUTWARD' THEN ABS(quantity) ELSE 0 END) as total_outward,
                SUM(quantity) as net_stock
            FROM inventory_ledger il
            JOIN receipts r ON il.receipt_id = r.id
            WHERE r.sender_phone = %s OR %s IS NULL
        """
        cur.execute(query, (sender_phone, sender_phone))
        return cur.fetchone()
    except Exception as e:
        print(f"❌ DB Global Stats Error: {e}")
        return {"total_inward": 0, "total_outward": 0, "net_stock": 0}
    finally:
        cur.close()
        conn.close()

def get_stock_by_profile(sender_phone: str = None):
    """Detailed breakdown of every cloth profile for the Live Stock Overview."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
            SELECT 
                cp.cloth_name,
                cp.shade_number,
                cp.width,
                cp.fabric_type,
                SUM(il.quantity) as available_qty,
                SUM(CASE WHEN il.movement_type = 'INWARD' THEN il.price_per_unit * il.quantity ELSE 0 END) as cost_valuation
            FROM cloth_profiles cp
            JOIN inventory_ledger il ON cp.id = il.cloth_profile_id
            JOIN receipts r ON il.receipt_id = r.id
            WHERE r.sender_phone = %s OR %s IS NULL
            GROUP BY cp.id, cp.cloth_name, cp.shade_number, cp.width, cp.fabric_type
            HAVING SUM(il.quantity) > 0
            ORDER BY available_qty ASC;
        """
        cur.execute(query, (sender_phone, sender_phone))
        return cur.fetchall()
    except Exception as e:
        print(f"❌ DB Stock Profile Error: {e}")
        return []
    finally:
        cur.close()
        conn.close()

# app/services/db.py

def get_inventory_details(sender_phone: str):
    """
    Fetches every single transaction for the detailed inventory view.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
    SELECT 
        fabric, 
        shade_code, 
        bale_no, 
        transaction_type, 
        meters, 
        thaans, 
        created_at 
    FROM inventory_ledger 
    WHERE sender_phone = %s 
    ORDER BY created_at DESC
    """
    
    try:
        cur.execute(query, (sender_phone,))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


# app/services/db.py

def get_stock_status_report(sender_phone: str, threshold_meters: float = 50.0, search_term: str = None):
    """
    Calculates live stock levels with an optional search filter.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Base query
    query = """
    SELECT 
        fabric, 
        shade_code, 
        SUM(CASE WHEN transaction_type = 'INWARD' THEN meters ELSE -meters END) as current_meters,
        SUM(CASE WHEN transaction_type = 'INWARD' THEN thaans ELSE -thaans END) as current_thaans
    FROM inventory_ledger
    WHERE sender_phone = %s
    """
    params = [sender_phone]
    
    # Add search filter if provided
    if search_term:
        query += " AND (fabric ILIKE %s OR shade_code ILIKE %s)"
        search_pattern = f"%{search_term}%"
        params.extend([search_pattern, search_pattern])
        
    query += " GROUP BY fabric, shade_code ORDER BY fabric ASC, shade_code ASC"
    
    try:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        
        report = []
        for row in rows:
            status = "HEALTHY"
            if row['current_meters'] <= 0:
                status = "OUT_OF_STOCK"
            elif row['current_meters'] < threshold_meters:
                status = "LOW_STOCK"
            
            report.append({**row, "status": status})
        return report
    finally:
        cur.close()
        conn.close()