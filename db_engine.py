import sqlite3

DB_PATH = "warehouse.db"

def get_filtered_data():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT tray_id, lane_code, location
            FROM tray_data
        """)

        rows = cursor.fetchall()

    result = []

    for tray, lane, rack in rows:
        if not rack:
            continue

        # 🔥 FILTERS
        try:
            rack_num = int(''.join(filter(str.isdigit, rack)))
        except:
            rack_num = 0

        if rack_num >= 42:
            continue

        if str(lane) == "16":
            continue

        result.append({
            "Tray Code": str(tray),
            "Current Rack Grp": str(rack),
            "Lane": str(lane)
        })

    return result