import time
import os
import json

FILE_PATH = "latest.json"
POLL_INTERVAL = 5

print(f"Starting polling service. Checking '{FILE_PATH}' every {POLL_INTERVAL} seconds...\n")

while True:
    if os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, "r", encoding="utf-8") as f:
                raw_data = f.read()
                
                if raw_data.strip():
                    # --- DO YOUR PROCESSING HERE ---
                    print(f"[{time.strftime('%X')}] Successfully read latest data.")
                    
                    # Example: If you want to parse it as JSON in this service
                    # data = json.loads(raw_data)
                    # print(f"Found keys: {list(data.keys())}")
                    
                    # For now, we'll just print the first 100 characters to prove it works
                    print(f"Preview: {raw_data[:100].strip()}...\n")
                else:
                    print(f"[{time.strftime('%X')}] File exists but is currently empty.\n")
                    
        except json.JSONDecodeError:
            print(f"[{time.strftime('%X')}] Error: Could not parse JSON. Incomplete write?\n")
        except Exception as e:
            print(f"[{time.strftime('%X')}] Error reading file: {e}\n")
    else:
        print(f"[{time.strftime('%X')}] Waiting for data... '{FILE_PATH}' not created yet.\n")
    
    # Wait 15 seconds before asking again
    time.sleep(POLL_INTERVAL)