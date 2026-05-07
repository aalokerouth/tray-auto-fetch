import os
import sys
import subprocess
import threading
import time
import winreg
import pymysql
import xml.etree.ElementTree as ET
import re

# --- Configuration ---
DEVICE_ID = "127.0.0.1:5555"
FILE_PATH = 'latest.json'
POLL_INTERVAL_SEC = 15
TRAY_PATTERN = re.compile(r"(\d+)\((\d+)\^\^(.*?)\^\^(.*?)\^\^\)")

# --- MySQL Configuration ---
MYSQL_HOST = "172.31.0.203"
MYSQL_USER = "dbadmin"          # Change to your MySQL username
MYSQL_PASS = "12345"      # Change to your MySQL password
MYSQL_DB   = "warehouse"     # Change to your database name

def get_db_connection():
    return pymysql.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASS,
        database=MYSQL_DB,
        autocommit=True
    )

# ==========================================
# 1. ADB DISCOVERY & CONNECTION
# ==========================================
def find_ldplayer_adb():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\XuanZhi\LDPlayer9") as key:
            install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
            adb_path = os.path.join(install_dir, "adb.exe")
            if os.path.exists(adb_path): return adb_path
    except WindowsError: pass

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\XuanZhi\LDPlayer") as key:
            install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
            adb_path = os.path.join(install_dir, "adb.exe")
            if os.path.exists(adb_path): return adb_path
    except WindowsError: pass

    common_paths = [r"C:\LDPlayer\LDPlayer9\adb.exe", r"D:\LDPlayer\LDPlayer9\adb.exe"]
    for path in common_paths:
        if os.path.exists(path): return path
    return None

def connect_adb(adb_path):
    print(f"[*] Connecting to ADB at: {DEVICE_ID}...")
    try:
        subprocess.run([adb_path, "connect", DEVICE_ID], check=True, stdout=subprocess.PIPE)
        print("[*] ADB Connected Successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[!] Failed to connect ADB: {e}")

# ==========================================
# 2. AUTO CLICKER LOGIC
# ==========================================
def adb_click(adb_path, x, y):
    subprocess.run([adb_path, "-s", DEVICE_ID, "shell", "input", "tap", str(x), str(y)], stderr=subprocess.DEVNULL)

def perform_sequence(adb_path, option_name, option_x, option_y):
    print(f"--- [Auto-Click] Sequence: {option_name} ---")
    adb_click(adb_path, 1175, 69)
    time.sleep(2)
    adb_click(adb_path, 465, 71)
    time.sleep(0.5) 
    adb_click(adb_path, option_x, option_y)

def run_auto_click_loop(adb_path):
    print("[*] Starting Auto-Clicker Loop...\n")
    while True:
        perform_sequence(adb_path, "PACK", 390, 90)
        time.sleep(7)
        perform_sequence(adb_path, "PICK", 390, 150)
        time.sleep(7)

# ==========================================
# 3. MySQL DATABASE SYNC LOGIC
# ==========================================
def init_db():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Create table if missing
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tray_data (
                    tray_id VARCHAR(50) PRIMARY KEY,
                    lane_code VARCHAR(50),
                    status INT,
                    user_name VARCHAR(100),
                    location VARCHAR(100),
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            ''')
            # Attempt to create index (ignore if already exists)
            try:
                cursor.execute('CREATE INDEX idx_lane ON tray_data(lane_code)')
            except Exception:
                pass
        conn.close()
        print("[*] MySQL Database initialized successfully.")
    except Exception as e:
        print(f"[!] Fatal DB Init Error: {e}")

def process_latest_data():
    if not os.path.exists(FILE_PATH): return

    try:
        with open(FILE_PATH, 'r', encoding='utf-8') as f:
            xml_content = f.read()

        root = ET.fromstring(xml_content)
        parsed_records = []
        
        for row in root.findall('row'):
            lane_code = row.find('c_lane_code').text
            trays_raw = row.find('c_tray_code').text
            
            if not trays_raw: continue
            
            for match in TRAY_PATTERN.finditer(trays_raw):
                tray_id = match.group(1)
                status = int(match.group(2))
                user_name = None if match.group(3) == "-" else match.group(3)
                location = None if match.group(4) == "-" else match.group(4)
                parsed_records.append((tray_id, lane_code, status, user_name, location))

        if parsed_records:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                # MySQL uses %s for placeholders, and ON DUPLICATE KEY UPDATE instead of ON CONFLICT
                sql = '''
                    INSERT INTO tray_data (tray_id, lane_code, status, user_name, location, last_updated)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE
                        lane_code = VALUES(lane_code), 
                        status = VALUES(status),
                        user_name = VALUES(user_name), 
                        location = VALUES(location),
                        last_updated = CURRENT_TIMESTAMP
                '''
                cursor.executemany(sql, parsed_records)
                
                # Cleanup missing locations
                cursor.execute("DELETE FROM tray_data WHERE location IS NULL OR TRIM(location) = ''")
                
            conn.close()
        print(f"[DB] Synced {len(parsed_records)} trays to MySQL @ 172.31.0.203")
    except Exception as e:
        print(f"[DB Error] {e}")

def run_tray_service():
    init_db()
    print(f"[*] Starting MySQL Sync Loop ({POLL_INTERVAL_SEC}s interval)...")
    while True:
        process_latest_data()
        time.sleep(POLL_INTERVAL_SEC)

# ==========================================
# 4. MITMPROXY RUNNER
# ==========================================
def run_mitmproxy():
    print("[*] Starting Mitmproxy Interceptors on port 8082...")
    try:
        subprocess.run(["mitmdump", "-p", "8082", "-s", "interceptor.py", "-s", "app.py"], stdout=sys.stdout, stderr=sys.stderr)
    except FileNotFoundError:
        print("[!] Error: 'mitmdump' not found.")

if __name__ == "__main__":
    print("=== WAREHOUSE AUTOMATION MASTER APP ===")
    
    adb_path = find_ldplayer_adb()
    if not adb_path:
        print("[!] CRITICAL ERROR: Could not locate LDPlayer adb.exe")
        sys.exit(1)
        
    connect_adb(adb_path)

    threading.Thread(target=run_mitmproxy, daemon=True).start()
    threading.Thread(target=run_tray_service, daemon=True).start()

    time.sleep(2)
    try:
        run_auto_click_loop(adb_path)
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")
        sys.exit(0)