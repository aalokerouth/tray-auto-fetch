import sys
import os
import playwright
from cx_Freeze import setup, Executable

# Find where Playwright's driver is installed
playwright_dir = os.path.dirname(playwright.__file__)
driver_dir = os.path.join(playwright_dir, "driver")

# Build options
build_exe_options = {
    # ADDED "pymysql" TO THIS LIST:
    "packages": ["PySide6", "pandas", "requests", "playwright", "openpyxl", "pymysql"],
    "include_files": [
        "config.json", 
        "presets.json", 
        "license.dat",
        "logo.ico",
        (os.path.join(playwright_dir, "driver"), "lib/playwright/driver"),
    ],
}

# The error fix: Use "gui" for Windows apps without a console
base_type = "gui" if sys.platform == "win32" else None

setup(
    name="TrayApp",
    version="1.3",
    description="Automated tray status fetcher and Telegram notifier",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "main_app.py", 
            base=base_type, 
            target_name="main_app.exe",
            icon="logo.ico"
        ),
        Executable(
            "playm.py", 
            base=base_type,
            target_name="playm.exe",
            icon="logo.ico"
        )
    ]
)