# app/services/db.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Establishes a connection to Supabase PostgreSQL."""
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def setup_database():
    """Creates the tables if they don't exist yet."""
    create_receipts_table = """
    CREATE TABLE IF NOT EXISTS receipts (
        id SERIAL PRIMARY KEY,
        transaction_type VARCHAR(50),
        total_thaans NUMERIC,
        total_meters NUMERIC,
        grand_total_amount NUMERIC,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    
    create_items_table = """
    CREATE TABLE IF NOT EXISTS line_items (
        id SERIAL PRIMARY KEY,
        receipt_id INTEGER REFERENCES receipts(id) ON DELETE CASCADE,
        sr_no INTEGER,
        fabric VARCHAR(255),
        thaans NUMERIC,
        meters NUMERIC,
        shade_code VARCHAR(50),
        price NUMERIC
    );
    """
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(create_receipts_table)
        cursor.execute(create_items_table)
        conn.commit()
        print("✅ PostgreSQL Tables Verified/Created.")
    except Exception as e:
        print(f"❌ DB Setup Error: {e}")
    finally:
        cursor.close()
        conn.close()

def insert_transaction(data):
    """Inserts the validated JSON from Gemini into the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Insert the main receipt summary
        summary = data.get('summary', {})
        cursor.execute(
            """
            INSERT INTO receipts (transaction_type, total_thaans, total_meters, grand_total_amount)
            VALUES (%s, %s, %s, %s) RETURNING id;
            """,
            (
                data.get('transaction_type'),
                summary.get('total_thaans'),
                summary.get('total_meters'),
                summary.get('grand_total_amount')
            )
        )
        receipt_id = cursor.fetchone()['id']
        
        # 2. Insert all the individual items linked to that receipt
        items = data.get('items', [])
        for item in items:
            cursor.execute(
                """
                INSERT INTO line_items (receipt_id, sr_no, fabric, thaans, meters, shade_code, price)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    receipt_id,
                    item.get('sr_no'),
                    item.get('fabric'),
                    item.get('thaans'),
                    item.get('meters'),
                    item.get('shade_code'),
                    item.get('price')
                )
            )
            
        conn.commit()
        print(f"💾 Successfully saved to Database! Receipt ID: {receipt_id}")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Database Insert Error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_inventory_summary(sender_phone: str = None):
    """
    Calculates total Inwards, Outwards, and Net Stock.
    If sender_phone is provided, it filters for that specific customer (requires adding sender_phone to receipts table).
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # SQL updated to use 'receipts' and 'line_items'
        # Note: If you want to filter by sender_phone, you'll need to add a sender_phone column to the receipts table
        # and include it in the insert_transaction logic. For now, this summarizes all data.
        query = """
            SELECT 
                r.transaction_type, 
                SUM(li.meters) as total_qty  -- Assuming 'meters' is the primary unit to track
            FROM receipts r
            JOIN line_items li ON r.id = li.receipt_id
            GROUP BY r.transaction_type
        """
        cur.execute(query) # Removed phone filter temporarily until schema supports it
        rows = cur.fetchall()
        
        stats = {
            "inward": 0,
            "outward": 0,
            "net_stock": 0
        }
        
        for row in rows:
            if row['transaction_type'] == 'INWARD':
                stats['inward'] = float(row['total_qty'] or 0)
            elif row['transaction_type'] == 'OUTWARD':
                stats['outward'] = float(row['total_qty'] or 0)
        
        stats['net_stock'] = stats['inward'] - stats['outward']
        
        return stats

    except Exception as e:
        print(f"❌ DB Summary Error: {e}")
        return None
    finally:
        cur.close()
        conn.close()

def get_inventory_details(sender_phone: str = None, limit: int = 50):
    """
    Fetches a detailed list of recent inventory items.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # SQL updated to use 'receipts' and 'line_items'
        query = """
            SELECT 
                r.transaction_type,
                r.created_at,
                li.fabric as item_description,
                li.meters as quantity,
                'Meters' as unit
            FROM line_items li
            JOIN receipts r ON li.receipt_id = r.id
            ORDER BY r.created_at DESC
            LIMIT %s
        """
        cur.execute(query, (limit,)) # Removed phone filter temporarily
        return cur.fetchall()

    except Exception as e:
        print(f"❌ DB Details Error: {e}")
        return []
    finally:
        cur.close()
        conn.close()