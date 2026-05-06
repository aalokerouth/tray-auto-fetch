import subprocess
import time

# Point directly to the ADB inside your LDPlayer folder
ADB_PATH = r"D:\LDPlayer\LDPlayer9\adb.exe"

# Make sure this matches the device ID you found earlier!
DEVICE_ID = "127.0.0.1:5555" 

def adb_click(x, y):
    """Sends a tap command to the specific emulator via ADB."""
    try:
        subprocess.run([ADB_PATH, "-s", DEVICE_ID, "shell", "input", "tap", str(x), str(y)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to click: {e}")
    except FileNotFoundError:
        print(f"ERROR: Could not find adb.exe at {ADB_PATH}. Check the path!")

def perform_sequence(option_name, option_x, option_y):
    """Executes the Refresh -> Dropdown -> Select cycle."""
    refresh_x, refresh_y = 1175, 69
    dropdown_x, dropdown_y = 465, 71
    
    print(f"--- Starting sequence for: {option_name} ---")
    
    # 1. Click Refresh and wait 2 seconds
    print("1. Clicking Refresh button...")
    adb_click(refresh_x, refresh_y)
    time.sleep(2)
    
    # 2. Click Dropdown and wait half a second for it to open
    print("2. Opening dropdown...")
    adb_click(dropdown_x, dropdown_y)
    time.sleep(0.5) 
    
    # 3. Click the specific Pick/Pack option
    print(f"3. Clicking '{option_name}'...")
    adb_click(option_x, option_y)
    print(f"Sequence '{option_name}' complete.")

if __name__ == "__main__":
    # Your precise coordinates for the menu options
    pack_x, pack_y = 390, 90
    pick_x, pick_y = 390, 150

    print("Starting alternating automation loop...\n")

    while True:
        # Do the PACK sequence
        perform_sequence("PACK", pack_x, pack_y)
        print("Waiting 7 seconds...\n")
        time.sleep(7)

        # Do the PICK sequence
        perform_sequence("PICK", pick_x, pick_y)
        print("Waiting 7 seconds...\n")
        time.sleep(7)