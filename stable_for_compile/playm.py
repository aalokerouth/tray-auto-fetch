from playwright.sync_api import sync_playwright
from datetime import datetime
from datetime import timedelta
import os
import sys

DOWNLOAD_DIR = r"D:\current tray"

def download_tray_status():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        page.goto("http://172.31.0.241:5006/user/home")
        page.wait_for_timeout(5000)

        # =========================
        # LOGIN
        # =========================
        def do_login():
            page.fill('input[type="text"]', "0246")
            page.fill('input[type="password"]', "123")
            page.click('button:has-text("SIGN IN")')

        if "login" in page.url:
            print("Login page detected")

            do_login()
            page.wait_for_timeout(2000)

            if "login" in page.url:
                print("Retrying login...")
                do_login()
                page.wait_for_timeout(3000)

        # =========================
        # SEARCH Tray Status
        # =========================
        search_box = page.locator('input[placeholder*="Search"]')
        search_box.click()
        search_box.fill("Tray Status")

        dropdown_item = page.locator("text=Tray Status").first
        dropdown_item.wait_for(timeout=5000)
        dropdown_item.click()

        # =========================
        # WAIT FOR PAGE
        # =========================
        page.wait_for_url("**/reports/**", timeout=15000)
        page.wait_for_timeout(3000)

        # =========================
        # BUSINESS DATE LOGIC
        # =========================
        if len(sys.argv) > 1:
            date_str = sys.argv[1]
        else:
            now = datetime.now()
            if now.hour < 9:
                now = now - timedelta(days=1)
            date_str = now.strftime("%Y-%m-%d")

        print(f"📅 Using date: {date_str}")

        # =========================
        # SET DATE & TIME USING KEYBOARD WORKAROUND
        # =========================
        print("👉 Resetting focus to Search box...")
        search_box = page.locator('input[placeholder*="Search"]')
        search_box.click()
        page.wait_for_timeout(500)

        print("👉 Pressing Tab 8 times to reach 'From Date'...")
        for _ in range(8):  
            page.keyboard.press("Tab")
            page.wait_for_timeout(100)

        print(f"👉 Typing From Date: {date_str}")
        page.keyboard.type(date_str)

        print("👉 Pressing Tab to reach 'To Date'...")
        page.keyboard.press("Tab")
        page.wait_for_timeout(100)

        print(f"👉 Typing To Date: {date_str}")
        page.keyboard.type(date_str)

        print("👉 Pressing Tab to reach 'From Time'...")
        page.keyboard.press("Tab")
        page.wait_for_timeout(100)

        print("👉 Typing From Time: 00:00:00")
        page.keyboard.type("00:00:00")

        print("👉 Pressing Tab TWICE to reach 'To Time'...")
        page.keyboard.press("Tab")
        page.wait_for_timeout(100)
        page.keyboard.press("Tab")
        page.wait_for_timeout(100)

        print("👉 Typing To Time: 23:59:59")
        page.keyboard.type("23:59:59")

        print("✅ Date and Time set seamlessly via keyboard")

        # =========================
        # CLICK SHOW BUTTON (KEYBOARD)
        # =========================
        print("👉 Tabbing to the Show button...")
        page.keyboard.press("Tab")
        page.wait_for_timeout(100)
        page.keyboard.press("Tab")  
        page.wait_for_timeout(100)

        print("👉 Pressing Enter to click Show...")
        page.keyboard.press("Enter")

        print("⏳ Waiting 10 seconds for data to process...")
        page.wait_for_timeout(10000)  # Hard pause instead of searching for a table

        # =========================
        # EXPORT USING KEYBOARD FLOW (17 TABS)
        # =========================
        print("👉 Reset focus via search bar...")
        search_box.click()
        page.wait_for_timeout(500)

        print("👉 TAB navigation to Export (17 times)...")
        for _ in range(21):
            page.keyboard.press("Tab")
            page.wait_for_timeout(100)

        print("👉 Pressing Enter to open Export menu...")
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)  # Short pause to let dropdown render

        print("👉 Pressing Enter again to select Excel and download...")

        # =========================
        # DOWNLOAD DETECTION
        # =========================
        try:
            with page.expect_download(timeout=90000) as download_info:
                page.keyboard.press("Enter")  # This triggers the download
            
            download = download_info.value
            
            # --- CUSTOM BUSINESS DAY LOGIC ---
            now = datetime.now()
            time_str = now.strftime('%H-%M-%S')
            
            # Create your final file path
            new_name = os.path.join(
                DOWNLOAD_DIR,
                f"tray_status_{date_str}_{time_str}.xlsx"
            )
            # ---------------------------------

            # Save the file
            download.save_as(new_name)
            print(f"🎉 SUCCESS: {new_name}")

        except Exception as e:
            print(f"❌ Download failed or timed out: {e}")

        finally:
            browser.close()

# Run the script
if __name__ == "__main__":
    download_tray_status()