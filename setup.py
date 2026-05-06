import sys
import os
import playwright
from cx_Freeze import setup, Executable

# Find where Playwright's driver is installed on your computer
playwright_dir = os.path.dirname(playwright.__file__)
driver_dir = os.path.join(playwright_dir, "driver")

# Tell it exactly which packages and non-code files to include
build_exe_options = {
    "packages": ["PySide6", "pandas", "requests", "playwright", "openpyxl"],
    "include_files": [
        "config.json", 
        "presets.json", 
        "license.dat",
        (driver_dir, "lib/playwright/driver")  # <-- THIS IS THE CRITICAL NEW LINE
    ],
    "excludes": []
}

# Hide the console for the main GUI, but keep it for the Playwright script
base_gui = "gui" if sys.platform == "win32" else None

setup(
    name="TrayApp",
    version="1.0",
    description="Tray Filter App",
    options={"build_exe": build_exe_options},
    executables=[
        Executable("main_app.py", base=base_gui, target_name="main_app.exe"),
        Executable("playm.py", base=None, target_name="playm.exe")
    ]
)