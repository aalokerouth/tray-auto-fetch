import json, os, hashlib, uuid, platform
from datetime import datetime
import base64


LICENSE_FILE = "license.dat"
DEV_SECRET = "Nandiniismylove@2004"

def get_hwid():
    raw = f"{uuid.getnode()}-{platform.system()}-{platform.processor()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_license():
    if not os.path.exists(LICENSE_FILE):
        return False, "Missing license", None

    try:
        raw = open(LICENSE_FILE).read()

        # 🔐 Decode
        decoded = base64.b64decode(raw).decode()
        lic = json.loads(decoded)

        expected_key = hashlib.sha256((lic["hwid"] + DEV_SECRET).encode()).hexdigest()

        if lic["key"] != expected_key:
            return False, "Invalid license key", lic

        if lic["hwid"] != get_hwid():
            return False, "HWID mismatch", lic

        if datetime.now() > datetime.fromisoformat(lic["expires"]):
            return False, "License expired", lic

        return True, "OK", lic

    except Exception as e:
        return False, f"Corrupt license: {str(e)}", None