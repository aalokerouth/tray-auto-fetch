import pymysql
import pandas as pd
import warnings

# Suppress pandas warning about not using SQLAlchemy
warnings.filterwarnings('ignore', 'pandas only supports SQLAlchemy connectable')

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
        cursorclass=pymysql.cursors.DictCursor
    )

def get_filtered_data():
    try:
        conn = get_db_connection()
        # =========================
        # LOAD DB FROM MYSQL
        # =========================
        # We order by last_updated so that drop_duplicates(keep="last") works correctly
        db_df = pd.read_sql("""
            SELECT
                tray_id,
                lane_code,
                location,
                last_updated
            FROM tray_data
            ORDER BY last_updated ASC
        """, conn)
        conn.close()
    except Exception as e:
        print(f"[!] Database connection error: {e}")
        return []

    # =========================
    # EMPTY SAFETY
    # =========================
    if db_df.empty:
        return []

    # =========================
    # CLEAN COLUMN TYPES
    # =========================
    db_df["tray_id"] = db_df["tray_id"].astype(str)
    db_df["lane_code"] = db_df["lane_code"].astype(str)
    db_df["location"] = db_df["location"].astype(str)

    # =========================
    # KEEP LATEST TRAY ONLY
    # =========================
    db_df = db_df.reset_index()

    db_df = db_df.drop_duplicates(
        subset=["tray_id"],
        keep="last"
    )

    # =========================
    # BUILD RESULT
    # =========================
    result = []

    for _, row in db_df.iterrows():

        tray = str(row["tray_id"]).strip()
        lane = str(row["lane_code"]).strip()
        rack = str(row["location"]).strip()

        if not tray or not rack:
            continue

        # =========================
        # FILTER RACK >= 42
        # =========================
        try:
            rack_num = int(''.join(filter(str.isdigit, rack)))

            if rack_num >= 42:
                continue

        except:
            pass

        # =========================
        # FILTER LANE 16
        # =========================
        if lane == "16":
            continue

        result.append({
            "Tray Code": tray,
            "Current Rack Grp": rack,
            "Lane": lane
        })

    return result