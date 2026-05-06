import os
import json
import requests
from datetime import datetime
import pandas as pd

# =====================================
# CONFIG
# =====================================
BOT_TOKEN = "8663778811:AAEqvTZYh8Lx6PocVh6zEVCEtF9I59VGdIo"
CHAT_ID = "-5070624209"

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# =====================================
# MESSAGE ID STORAGE
# =====================================
MSG_FILE = "telegram_messages.json"


def load_message_ids():
    if os.path.exists(MSG_FILE):
        try:
            with open(MSG_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}



def save_message_ids(data):
    with open(MSG_FILE, "w") as f:
        json.dump(data, f, indent=2)


# =====================================
# SEND NEW MESSAGE
# =====================================
def send_new(text, preset_name=None):
    url = f"{BASE_URL}/sendMessage"

    try:
        res = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": text,
            },
            timeout=10,
        )

        data = res.json()

        if data.get("ok"):
            msg_id = data["result"]["message_id"]

            # save preset -> msg id mapping
            if preset_name:
                saved = load_message_ids()
                saved[preset_name] = msg_id
                save_message_ids(saved)

            return msg_id

        print(f"[TELEGRAM ERROR] {data}")
        return None

    except requests.exceptions.RequestException as e:
        print(f"[TELEGRAM ERROR] {e}")
        return None


# =====================================
# EDIT EXISTING MESSAGE
# =====================================
def edit(msg_id, text):
    url = f"{BASE_URL}/editMessageText"

    try:
        res = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "message_id": msg_id,
                "text": text,
            },
            timeout=10,
        )

        data = res.json()

        if not data.get("ok"):

            # ignore identical message edits
            if "message is not modified" in str(data).lower():
                return data

            print(f"[TELEGRAM ERROR] {data}")

        return data

    except requests.exceptions.RequestException as e:
        print(f"[TELEGRAM ERROR] {e}")
        return None


# =====================================
# GET MESSAGE ID FOR PRESET
# =====================================
def get_message_id(preset_name):
    data = load_message_ids()
    return data.get(preset_name)


# =====================================
# SAVE MESSAGE ID FOR PRESET
# =====================================
def save_message_id(preset_name, msg_id):
    data = load_message_ids()
    data[preset_name] = msg_id
    save_message_ids(data)


# =====================================
# BUILD TELEGRAM MESSAGE
# =====================================
def build_message(preset_name, rack_map, edited=False):

    from datetime import datetime

    MAX_LEN = 3900

    now = datetime.now().strftime("%H:%M:%S")

    slot_text = ""

    if isinstance(rack_map, dict):

        # try to get slot info from hidden metadata
        slots = rack_map.get("__slots__", [])

        if slots:
            slot_text = f" [{', '.join(slots)}]"

    title = f"📦 {preset_name}{slot_text}"

    if edited:
        title = f" {title}"

    lines = [title]

    for rack, trays in rack_map.items():

        if not trays:
            continue

        # compact format
        tray_text = ",".join(map(str, trays))

        line = f"{rack}:{tray_text}"

        temp = "\n".join(lines + [line])

        # stop BEFORE overflow
        if len(temp) > MAX_LEN:
            break

        lines.append(line)

    return "\n".join(lines)


# =====================================
# SORT RACKS
# =====================================
def rack_sort_key(rack):
    import re

    if str(rack).lower() == "highway":
        return (999, "Z")

    match = re.match(r"(\d+)([A-Z]?)", str(rack))

    if match:
        num = int(match.group(1))
        letter = match.group(2) or ""
        return (num, letter)

    return (999, str(rack))


# =====================================
# BUILD RACK MAP FROM DATAFRAME
# =====================================
def build_rack_map(df):
    """
    Expected columns:
    - Tray Code
    - Current Rack Grp
    - Order Count
    """

    rack_map = {}

    if df is None or df.empty:
        return rack_map

    for _, row in df.iterrows():
        try:
            tray = str(row.get("Tray Code", "")).strip()
            rack = row.get("Current Rack Grp", "")

            if pd.isna(rack):
                rack = "HW"

            rack = str(rack).strip()

            if rack.lower() == "nan":
                rack = "HW"

            if not tray or not rack:
                continue

            # skip invalid
            if rack.startswith("42"):
                continue

            # skip lane 16
            if rack.startswith("16"):
                continue

            count = row.get("Order Count", 1)

            try:
                count = int(count)
            except:
                count = 1

            display_tray = f"{tray} ({count})"

            # =========================
            # PICKING DONE FROM DB
            # =========================
            # lane = str(row.get("Lane", row.get("lane_code", "")))

            # try:
            #     lane_num = int(''.join(filter(str.isdigit, lane)))

            #     if 17 <= lane_num <= 30:
            #         display_tray += " [Picking Done]"

            # except:
            #     pass


            rack_map.setdefault(rack, []).append(display_tray)

        except Exception as e:
            print(f"[RACK MAP ERROR] {e}")

    # sort racks properly
    sorted_map = {}

    for rack in sorted(rack_map.keys(), key=rack_sort_key):
        sorted_map[rack] = rack_map[rack]

    return sorted_map


# =====================================
# SEND OR EDIT PRESET MESSAGE
# =====================================
def send_or_edit_preset(preset_name, rack_map, edited=False):

    if not rack_map:
        return

    text = build_message(
        preset_name,
        rack_map,
        edited=edited
    )

    msg_id = get_message_id(preset_name)

    # =========================
    # EDIT EXISTING
    # =========================
    if msg_id:

        res = edit(msg_id, text)

        if res and res.get("ok"):
            return msg_id

    # =========================
    # SEND NEW
    # =========================
    new_id = send_new(text, preset_name=preset_name)

    if new_id:
        save_message_id(preset_name, new_id)

    return new_id