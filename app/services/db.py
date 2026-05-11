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