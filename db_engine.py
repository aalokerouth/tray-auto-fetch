import sqlite3
import pandas as pd

DB_PATH = "fetch/warehouse.db"


def get_filtered_data():

    with sqlite3.connect(DB_PATH) as conn:

        # =========================
        # LOAD DB
        # =========================
        db_df = pd.read_sql("""
            SELECT
                tray_id,
                lane_code,
                location
            FROM tray_data
        """, conn)

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
    # IMPORTANT:
    # SQLite rowid newest = latest update
    # so keep LAST duplicate
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