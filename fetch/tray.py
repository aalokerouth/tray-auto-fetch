import sqlite3
import xml.etree.ElementTree as ET
import re
import time
import os

# --- Configuration ---
FILE_PATH = 'latest.json'
DB_PATH = 'warehouse.db'
POLL_INTERVAL_SEC = 15

# Pre-compile regex for maximum speed
# Matches: 22421(0^^Amit Hazra^^27A^^)
TRAY_PATTERN = re.compile(r"(\d+)\((\d+)\^\^(.*?)\^\^(.*?)\^\^\)")

def init_db():
    """Initialize the SQLite database with an upsert-ready schema."""
    with sqlite3.connect(DB_PATH) as conn:
        # We use tray_id as the primary key so we can easily UPDATE changing data
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tray_data (
                tray_id TEXT PRIMARY KEY,
                lane_code TEXT,
                status INTEGER,
                user_name TEXT,
                location TEXT,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Adding an index on user_name or location can be done here if needed for fast queries
        conn.execute('CREATE INDEX IF NOT EXISTS idx_lane ON tray_data(lane_code)')

def process_latest_data():
    """Reads the file, parses the data, and bulk inserts into SQLite."""
    if not os.path.exists(FILE_PATH):
        print(f"[{time.strftime('%X')}] Waiting for file: {FILE_PATH}")
        return

    start_time = time.time()

    try:
        # 1. Read file quickly
        with open(FILE_PATH, 'r', encoding='utf-8') as f:
            xml_content = f.read()

        # 2. Parse XML
        root = ET.fromstring(xml_content)
        parsed_records = []
        
        # 3. Extract and parse data
        for row in root.findall('row'):
            lane_code = row.find('c_lane_code').text
            trays_raw = row.find('c_tray_code').text
            
            if not trays_raw:
                continue
            
            # Use finditer for zero-allocation high-speed matching
            for match in TRAY_PATTERN.finditer(trays_raw):
                tray_id = match.group(1)
                status = int(match.group(2))
                user_name = None if match.group(3) == "-" else match.group(3)
                location = None if match.group(4) == "-" else match.group(4)
                
                # Append tuple matching the INSERT statement order
                parsed_records.append((tray_id, lane_code, status, user_name, location))

        # 4. Bulk Upsert into SQLite
        if parsed_records:
            with sqlite3.connect(DB_PATH) as conn:
                # executemany processes the entire batch in C-level loop (Extremely fast)
                conn.executemany('''
                    INSERT INTO tray_data (tray_id, lane_code, status, user_name, location, last_updated)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(tray_id) DO UPDATE SET
                        lane_code = excluded.lane_code,
                        status = excluded.status,
                        user_name = excluded.user_name,
                        location = excluded.location,
                        last_updated = CURRENT_TIMESTAMP
                ''', parsed_records)

        elapsed = time.time() - start_time
        print(f"[{time.strftime('%X')}] Processed {len(parsed_records)} trays in {elapsed:.4f} seconds.")

    except Exception as e:
        print(f"[{time.strftime('%X')}] Error processing file: {e}")

def run_service():
    """Runs continuously as a background service."""
    init_db()
    print(f"Starting Data Processing Service. Polling every {POLL_INTERVAL_SEC} seconds...")
    
    while True:
        process_latest_data()
        time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    run_service()