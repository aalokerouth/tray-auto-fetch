from datetime import datetime, timedelta
import sys, os, json, threading, time
from turtle import right
import pandas as pd
from db_engine import get_filtered_data
import telegram_engine
import hashlib
from PySide6.QtWidgets import *
from PySide6.QtCore import QEvent, QSize, Qt, QAbstractTableModel, QTimer
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QWidgetAction
from PySide6.QtWidgets import QInputDialog
from license_system import validate_license
from PySide6.QtWidgets import QStyledItemDelegate

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QStyleOptionButton, QStyle
from PySide6.QtGui import QPalette
from PySide6.QtGui import QBrush
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtGui import QPainter
try:
    from playm import download_tray_status
except:
    download_tray_status = None


CONFIG_FILE = "config.json"
PRESET_FILE = "presets.json"

DISPLAY_COLUMNS = [
    "Tray Code", "Current Rack Grp", "Order Count",
    "Pl No", "Route Type", "Routetype", "Order Type"
]

def get_shift_now():
    now = datetime.now()

    # if now.hour < 9:
    #     now = now - timedelta(days=1)

    return now.time()

def get_business_date(preset=None):
    now = datetime.now()

    # 🔥 preset override
    if preset and preset.get("use_prev_day_until_9"):
        if now.hour < 9:
            return now - timedelta(days=1)
        return now

    # 🔥 default fallback (same behavior)
    if now.hour < 9:
        return now - timedelta(days=1)
    return now
# =========================
# LICENSE CHECK
# =========================
def background_check():
    while True:
        ok, _, _ = validate_license()
        if not ok:
            os._exit(1)
        time.sleep(12)

class RightCheckDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        style = option.widget.style()

        # Base item
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.features &= ~QStyleOptionViewItem.HasCheckIndicator

        # leave space for checkbox
        opt.rect = option.rect.adjusted(0, 0, -50, 0)

        style.drawControl(QStyle.CE_ItemViewItem, opt, painter)

        # Hover effect
        if option.state & QStyle.State_MouseOver:
            painter.save()
            painter.setBrush(QColor(255, 255, 255, 20))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(option.rect.adjusted(2, 2, -2, -2), 8, 8)
            painter.restore()

        checked = index.data(Qt.CheckStateRole) == Qt.Checked

        # Selected background
        if checked:
            painter.save()
            painter.setBrush(QColor("#238636"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(option.rect.adjusted(2, 2, -2, -2), 8, 8)
            painter.restore()


        # 🔥 CUSTOM CHECKBOX (MANUAL DRAW — BEST CONTROL)
        rect = option.rect
        cb_rect = QRect(rect.right() - 40, rect.top() + 8, 22, 22)

        painter.save()

        # Box
        painter.setPen(QColor("#8b949e"))
        painter.setBrush(QColor("#30363d") if not checked else QColor("#3fb950"))
        painter.drawRoundedRect(cb_rect, 4, 4)

        # Tick
        if checked:
            painter.setPen(QColor("#ffffff"))
            painter.drawText(cb_rect, Qt.AlignCenter, "✔")

        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease:
            rect = option.rect
            cb_rect = QRect(rect.right() - 40, rect.top() + 8, 22, 22)

            if cb_rect.contains(event.position().toPoint()):
                current = index.data(Qt.CheckStateRole)
                new_state = Qt.Unchecked if current == Qt.Checked else Qt.Checked

                model.setData(index, new_state, Qt.CheckStateRole)
                option.widget.viewport().update()
                return True

        return super().editorEvent(event, model, option, index)

# =========================
# TABLE MODEL
# =========================
class PandasModel(QAbstractTableModel):
    def __init__(self, df, alert_rows=None):
        super().__init__()
        self.df = df
        self.alert_rows = alert_rows or set()
        self.flash_state = True
        self.flash_level = 0
        self.flash_direction = 1
        
        # 🔥 OPTIMIZATION: Cache raw data & indices for 100x faster rendering
        self._data = df.values
        self._columns = df.columns.tolist()
        self.order_type_col = self._columns.index("Order Type") if "Order Type" in self._columns else -1

    def rowCount(self, parent=None):
        return len(self.df)

    def columnCount(self, parent=None):
        return len(self._columns)

    def data(self, index, role):
        if not index.isValid():
            return None
            
        row = index.row()
        col = index.column()

        # 🔥 FAST ACCESS: Bypass pandas .iloc completely
        value = self._data[row, col]

        if role == Qt.DisplayRole:
            return str(value)

        # 🎨 BACKGROUND COLORS
        if role == Qt.BackgroundRole:
            if row in self.alert_rows:
                return QColor(self.flash_level, 0, 0)

            if self.order_type_col != -1:
                order_type = str(self._data[row, self.order_type_col]).upper()
                if "B2B" in order_type:
                    return QColor("#FFA500")
                elif "B2C" in order_type:
                    return QColor("#FF4D4D")
                elif "IWT" in order_type:
                    return QColor("#3FB950")

        # 🔠 TEXT COLOR
        if role == Qt.ForegroundRole:
            if row in self.alert_rows:
                return QBrush(QColor("white"))
            if self.order_type_col != -1:
                order_type = str(self._data[row, self.order_type_col]).upper()
                if "B2C" in order_type:
                    return QBrush(QColor("white"))

        return None

    def toggle_flash(self):
        if not self.alert_rows:
            return

        self.flash_level += self.flash_direction * 25

        if self.flash_level >= 255:
            self.flash_level = 255
            self.flash_direction = -1
        elif self.flash_level <= 80:
            self.flash_level = 80
            self.flash_direction = 1

        row_count = self.rowCount()
        col_count = self.columnCount()

        if row_count == 0 or col_count == 0:
            return

        # 🔥 SAFE repaint
        for row in self.alert_rows:
            if row < 0 or row >= row_count:
                continue  # 🚫 skip invalid rows

            top_left = self.index(row, 0)
            bottom_right = self.index(row, col_count - 1)

            if top_left.isValid() and bottom_right.isValid():
                self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole])

    def headerData(self, col, orientation, role):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._columns[col]
        

# =========================
# MULTISELECT DROPDOWN
# =========================
class MultiSelectCombo(QPushButton):
    def __init__(self, parent, key):
        super().__init__("All")
        self.parent_widget = parent
        self.key = key

        self.menu = QMenu(self)
        self.setMenu(self.menu)

        self.actions = []

    def populate(self, values, selected):
        self.menu.clear()
        self.actions = []

        # 🔍 Search box
        search_action = QWidgetAction(self.menu)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")
        self.search_box.textChanged.connect(self.filter_items)
        search_action.setDefaultWidget(self.search_box)
        self.menu.addAction(search_action)

        # ✔ Select All
        select_all = QAction("Select All", self)
        select_all.triggered.connect(self.select_all)
        self.menu.addAction(select_all)

        # ❌ Clear All
        clear_all = QAction("Clear All", self)
        clear_all.triggered.connect(self.clear_all)
        self.menu.addAction(clear_all)

        self.menu.addSeparator()

        for v in sorted([str(v) for v in values]):
            act = QAction(v, self)
            act.setCheckable(True)
            act.setChecked(v in selected)
            act.toggled.connect(self.update_selection)
            self.menu.addAction(act)
            self.actions.append(act)

        self.update_text()

    def filter_items(self, text):
        text = text.lower()
        for act in self.actions:
            act.setVisible(text in act.text().lower())

    def select_all(self):
        for a in self.actions:
            a.setChecked(True)

    def clear_all(self):
        for a in self.actions:
            a.setChecked(False)

    def update_selection(self):
        selected = [a.text() for a in self.actions if a.isChecked()]
        self.parent_widget.filters[self.key] = selected
        self.update_text()
        self.parent_widget.apply_filters()

    def update_text(self):
        selected = [a.text() for a in self.actions if a.isChecked()]
        if not selected:
            self.setText("All")
        elif len(selected) <= 2:
            self.setText(", ".join(selected))
        else:
            self.setText(f"{selected[0]}, {selected[1]} (+{len(selected)-2})")

# =========================
# PROCESS DATA
# =========================


def process_df(df):
    df.columns = df.iloc[0]
    df = df[1:].reset_index(drop=True)
    df.columns = df.columns.astype(str).str.strip()

    def find(k):
        return [c for c in df.columns if k in c.lower()]

    rack = find("rack")
    tray = find("tray")
    route = find("route")

    if rack:
        df.rename(columns={rack[0]: "Current Rack Grp"}, inplace=True)
    if tray:
        df.rename(columns={tray[0]: "Tray Code"}, inplace=True)
    if len(route) >= 1:
        df.rename(columns={route[0]: "Route Type"}, inplace=True)
    if len(route) >= 2:
        df.rename(columns={route[1]: "Routetype"}, inplace=True)

    if "Tray Code" in df.columns:
        df = df.drop_duplicates(subset=["Tray Code"])

    df = df[df["Current Rack Grp"].notna()]
    df = df[df["Current Rack Grp"] != ""]

    # Replaces "-" with highway nigga
    df["Current Rack Grp"] = df["Current Rack Grp"].replace("-", "HW")

    return df

# =========================
# MAIN APP
# =========================
class App(QMainWindow):
    def __init__(self):
        super().__init__()

        self.is_running = False
        self.last_hash = None
        self.last_play_time = 0

        from PySide6.QtGui import QFont

        font = QFont()
        font.setFamily("Segoe UI")
        font.setPointSize(max(8, 10))
        self.setFont(font)
        self.setWindowTitle("Tray Filter App")
        self.resize(1500, 850)

        self.config = self.load_json(CONFIG_FILE)
        self.presets = self.load_json(PRESET_FILE)

        self.filters = {
            "order_type": [],
            "route_type": [],
            "slot": [],
            "order_class": []
        }

        # ✅ CREATE FILTER WIDGETS HERE (FIX)
        self.order = MultiSelectCombo(self, "order_type")
        self.route = MultiSelectCombo(self, "route_type")
        self.slot = MultiSelectCombo(self, "slot")
        self.cls = MultiSelectCombo(self, "order_class")

        self.df = None
        self.filtered_df = None

        self.dark = True
        self.apply_dark()

        self.init_ui()
        # self.load_files()
        self.update_license_status()
        self.license_timer = QTimer()
        self.license_timer.timeout.connect(self.update_license_status)
        self.license_timer.start(60000)

        # AUTO REFRESH
        # self.timer = QTimer()
        # self.timer.timeout.connect(self.auto_refresh)
        # self.timer.start(15000)

        self.realtime_timer = QTimer()
        self.realtime_timer.timeout.connect(self.realtime_update)
        self.realtime_timer.start(20000)  # 20 sec

    # =========================
    # UI
    # =========================
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # ===== SIDEBAR =====
        side = QVBoxLayout()
        side.setSpacing(10)

        # FILE SELECT
        self.file_box = QComboBox()
        self.file_box.currentIndexChanged.connect(self.load_file)

        self.theme_btn = QPushButton("Toggle Theme")
        self.theme_btn.clicked.connect(self.toggle_theme)

        file_group = QGroupBox("File")
        file_layout = QVBoxLayout()
        file_layout.addWidget(self.file_box)

        # 🔥 SETTINGS BUTTON (small)
        settings_layout = QHBoxLayout()
        
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setFixedWidth(40)
        self.theme_btn.clicked.connect(self.toggle_theme)
        
        self.settings_btn = QPushButton("📂")
        self.settings_btn.setFixedWidth(40)
        self.settings_btn.clicked.connect(self.change_folder)
        
        settings_layout.addWidget(self.theme_btn)
        settings_layout.addWidget(self.settings_btn)
        
        file_layout.addLayout(settings_layout)
        file_group.setLayout(file_layout)
        side.addWidget(file_group)

        # FILTERS
        filter_group = QGroupBox("Filters")
        filter_layout = QVBoxLayout()

        filter_layout.addWidget(QLabel("Order Type"))
        filter_layout.addWidget(self.order)

        filter_layout.addWidget(QLabel("Route Type"))
        filter_layout.addWidget(self.route)

        filter_layout.addWidget(QLabel("Slot"))
        filter_layout.addWidget(self.slot)

        filter_layout.addWidget(QLabel("Order Class"))
        filter_layout.addWidget(self.cls)

        filter_group.setLayout(filter_layout)
        side.addWidget(filter_group)

        # PRESETS
        preset_group = QGroupBox("Presets")
        preset_layout = QVBoxLayout()

        self.preset_box = QComboBox()
        self.preset_box.addItems([""] + list(self.presets.keys()))

        btn_load = QPushButton("Load")
        btn_save = QPushButton("Save")

        btn_load.clicked.connect(self.load_preset)
        btn_save.clicked.connect(self.save_preset)

        preset_layout.addWidget(self.preset_box)
        preset_layout.addWidget(btn_load)
        preset_layout.addWidget(btn_save)

        preset_group.setLayout(preset_layout)
        side.addWidget(preset_group)

        side.addStretch()

        layout.addLayout(side, 1)

        # ===== RIGHT PANEL =====
        right = QVBoxLayout()

        #  ALERT BANNER
        self.alert_banner = QLabel("")
        self.alert_banner.setStyleSheet("""
            background-color: #8B0000;
            color: white;
            font-weight: bold;
            padding: 8px;
            border-radius: 6px;
        """)
        self.alert_banner.setVisible(False)
        
        right.addWidget(self.alert_banner)

        # =========================
        # 📊 METRICS BAR
        # =========================
        metrics_layout = QHBoxLayout()

        self.total_label = QLabel("Total: 0")
        self.filtered_label = QLabel("Filtered: 0")
        self.rack_count_label = QLabel("Racks: 0")

        self.total_label.setStyleSheet("color:#58a6ff; font-weight:bold;")
        self.filtered_label.setStyleSheet("color:#3fb950; font-weight:bold;")
        self.rack_count_label.setStyleSheet("color:#f2cc60; font-weight:bold;")

        metrics_layout.addWidget(self.total_label)
        metrics_layout.addWidget(self.filtered_label)
        metrics_layout.addWidget(self.rack_count_label)

        right.addLayout(metrics_layout)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search Tray Code")
        self.search.textChanged.connect(self.apply_filters)
        right.addWidget(self.search)

        self.remove_st = QCheckBox("Remove ST trays")
        self.remove_st.setChecked(True)
        self.remove_st.stateChanged.connect(self.apply_filters)
        right.addWidget(self.remove_st)

        self.remove_non_ptl = QCheckBox("PTL only")
        self.remove_non_ptl.setChecked(True)
        self.remove_non_ptl.stateChanged.connect(self.apply_filters)
        right.addWidget(self.remove_non_ptl)

        self.active_rack_label = QLabel("All Racks")
        self.active_rack_label.setStyleSheet("color:#58a6ff; font-weight:bold;")
        right.addWidget(self.active_rack_label)

        right.addWidget(QLabel("Rack Summary"))
        rack_btn_layout = QHBoxLayout()

        btn_all = QPushButton("Select All")
        btn_none = QPushButton("Clear")
        btn_print = QPushButton("🖨")   # small icon button
        btn_print.setFixedWidth(40)

        btn_all.clicked.connect(self.select_all_racks)
        btn_none.clicked.connect(self.clear_all_racks)
        btn_print.clicked.connect(self.print_selected_racks_pdf)

        rack_btn_layout.addWidget(btn_all)
        rack_btn_layout.addWidget(btn_none)
        rack_btn_layout.addWidget(btn_print)

        right.addLayout(rack_btn_layout)
        self.rack_list = QListWidget()
        self.rack_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.rack_list.itemChanged.connect(self.filter_rack)
        right.addWidget(self.rack_list)

        self.rack_list.setItemDelegate(RightCheckDelegate())

        self.table = QTableView()
        self.table.setSortingEnabled(True)
        right.addWidget(self.table)

        btn_layout = QHBoxLayout()

        btn_details = QPushButton("Show Details")
        btn_details.clicked.connect(self.show_tray_details)
        btn_layout.addWidget(btn_details)

        btn_export = QPushButton("Export View")
        btn_export.clicked.connect(self.export_view)

        btn_rack = QPushButton("Rack-wise Export")
        btn_rack.clicked.connect(self.export_rack)

        btn_notify = QPushButton("Force Telegram Update")
        btn_notify.clicked.connect(self.realtime_update)

        btn_auto = QPushButton("Run All Presets")
        btn_auto.clicked.connect(self.run_all_presets)

        btn_run_pw = QPushButton("Start Auto Download")
        btn_run_pw.clicked.connect(self.start_playwright_loop)

        btn_stop_pw = QPushButton("Stop Auto Download")
        btn_stop_pw.clicked.connect(self.stop_playwright_loop)


        

        btn_layout.addWidget(btn_notify)
        btn_layout.addWidget(btn_export)
        btn_layout.addWidget(btn_rack)
        btn_layout.addWidget(btn_auto)
        btn_layout.addWidget(btn_run_pw)
        btn_layout.addWidget(btn_stop_pw)

        right.addLayout(btn_layout)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        right.addWidget(self.log_box)

        btn_layout.addWidget(btn_export)
        # btn_layout.addWidget(btn_rack)

        layout.addLayout(right, 3)
        self.rack_list.setSpacing(6)
        self.rack_list.setUniformItemSizes(True)

        # =========================
        # 🔐 LICENSE STATUS
        # =========================
        self.license_label = QLabel("License: Checking...")
        self.license_label.setStyleSheet("color:#58a6ff; font-weight:bold;")
        right.addWidget(self.license_label)

        #  FLASH TIMER (after table is created)
        self.flash_timer = QTimer()
        self.flash_timer.timeout.connect(self.flash_alert_rows)

    def apply_preset_filter_df(self, df, preset):
        import pandas as pd
        from datetime import datetime

        filtered = df.copy()

        # ORDER TYPE
        if preset.get("order_type") and "Order Type" in filtered.columns:
            filtered = filtered[filtered["Order Type"].isin(preset["order_type"])]

        # ROUTE TYPE
        if preset.get("route_type") and "Route Type" in filtered.columns:
            filtered = filtered[filtered["Route Type"].isin(preset["route_type"])]

        # SLOT → mapped to Routetype
        if preset.get("slot") and "Routetype" in filtered.columns:
            filtered = filtered[filtered["Routetype"].isin(preset["slot"])]

        # ORDER CLASS
        if preset.get("order_class") and "Order Class" in filtered.columns:
            filtered = filtered[filtered["Order Class"].isin(preset["order_class"])]

        # TIME FILTER
        if "Changed On" in filtered.columns:
            filtered["Changed On"] = pd.to_datetime(filtered["Changed On"], errors="coerce")
            filtered = filtered.dropna(subset=["Changed On"])

            from_time = datetime.strptime(preset["from_time"], "%H:%M:%S").time()
            to_time = datetime.strptime(preset["to_time"], "%H:%M:%S").time()

            def in_time_range(ts):
                t = ts.time()
                if from_time <= to_time:
                    return from_time <= t <= to_time
                else:
                    return t >= from_time or t <= to_time

            filtered = filtered[filtered["Changed On"].apply(in_time_range)]

        return filtered
  

    # =========================
    # THEMES
    # =========================
    def apply_dark(self):
        self.setStyleSheet("""
        QWidget {
            background: #0d1117;
            color: #e6edf3;
            font-size: 14px;
            font-family: Segoe UI;
        }

        QGroupBox {
            font-size: 15px;
            font-weight: bold;
            border: 1px solid #30363d;
            border-radius: 8px;
            margin-top: 10px;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }

        QPushButton {
            background-color: #21262d;
            border: 1px solid #30363d;
            padding: 6px 10px;
            border-radius: 6px;
        }

        QPushButton:hover {
            background-color: #30363d;
        }

        QLineEdit {
            background: #161b22;
            border: 1px solid #30363d;
            padding: 6px;
            border-radius: 6px;
        }

        QListWidget {
            border: none;
            outline: none;
        }

        /* 🔥 CARD STYLE ITEMS */
        QListWidget::item {
            background: #161b22;
            margin: 4px;
            padding: 10px;
            border-radius: 8px;
        }

        QListWidget::item:hover {
            background: #1f2937;
        }

        QListWidget::item:selected {
            background: #238636;
        }

        /* 🔥 BIGGER CHECKBOX */
        QCheckBox::indicator {
            width: 20px;
            height: 20px;
        }

        QCheckBox::indicator:unchecked {
            border: 2px solid #8b949e;
            background: #0d1117;
        }

        QCheckBox::indicator:checked {
            background: #3fb950;
            border: 2px solid #3fb950;
        }

        QTableView {
            background: #0d1117;
            gridline-color: #30363d;
        }
        """)
        
    def start_playwright_loop(self):
        if self.is_running:
            self.log("[SKIP] Already running")
            return

        self.is_running = True
        self.log("[START] Scheduler started")

        # Trigger the first run 1 second from now so the UI doesn't freeze instantly
        QTimer.singleShot(1000, self.run_scheduler_cycle)

    def run_scheduler_cycle(self):
        if not self.is_running:
            return

        now = datetime.now().time()

        # 🔥 Decide interval in minutes
        if now.hour >= 21 or now.hour < 9:
            interval_minutes = 7
        else:
            interval_minutes = 12

        self.log(f"[RUN] Scheduler cycle at {datetime.now().strftime('%H:%M:%S')}")

        # 🔥 RUN PRESETS (SAFE - MAIN THREAD)
        self.run_all_presets()

        # 🔥 Queue the NEXT cycle using singleShot (immune to garbage collection)
        if self.is_running:
            self.log(f"[SLEEP] {interval_minutes} mins")
            # Convert minutes to milliseconds for the timer
            QTimer.singleShot(interval_minutes * 60 * 1000, self.run_scheduler_cycle)

    def stop_playwright_loop(self):
        self.is_running = False
        self.log("[STOP] Scheduler stopped")

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(f"[{timestamp}] {msg}")

    def wait_non_blocking(self, seconds):
        """Pauses the script without freezing the GUI event loop"""
        from PySide6.QtCore import QEventLoop
        loop = QEventLoop()
        QTimer.singleShot(int(seconds * 1000), loop.quit)
        loop.exec()


    def show_tray_details(self):
        if self.filtered_df is None:
            return

        tray, ok = QInputDialog.getText(self, "Tray", "Enter Tray Code")

        if not ok or not tray:
            return

        if not hasattr(self, "raw_df"):
            QMessageBox.warning(self, "Error", "Raw data not loaded")
            return

        try:
            raw = self.raw_df.copy()

            # ✅ FIXED: no double header
            raw.columns = raw.columns.astype(str).str.strip()

            # ✅ STRICT tray column detection
            tray_col = None
            for c in raw.columns:
                if c.lower().replace(" ", "") == "traycode":
                    tray_col = c
                    break

            if not tray_col:
                QMessageBox.warning(self, "Error", "Tray column not found")
                return

            tray = tray.strip()

            df = raw[
                raw[tray_col].astype(str).str.strip() == tray
            ]

            if df.empty:
                QMessageBox.information(self, "Info", "No data found")
                return

            cols = [c for c in ["Orderid", "Routetype", "Slot", "Tray Completed Time"] if c in df.columns]

            if not cols:
                text = df.to_string(index=False)
            else:
                display_df = df[cols].copy()

                # 🔥 Replace missing times
                if "Tray Completed Time" in display_df.columns:
                    display_df["Tray Completed Time"] = (
                        display_df["Tray Completed Time"]
                        .fillna("Not picked yet")
                        .replace("", "Not picked yet")
                    )

                text = display_df.to_string(index=False)

            dialog = QDialog(self)
            dialog.setWindowTitle(f"Details for {tray}")
            dialog.resize(700, 500)

            layout = QVBoxLayout(dialog)

            text_box = QTextEdit()
            text_box.setReadOnly(True)
            text_box.setText(text)

            layout.addWidget(text_box)

            btn = QPushButton("Close")
            btn.clicked.connect(dialog.close)
            layout.addWidget(btn)

            dialog.exec()

        except Exception as e:
            self.log(f"[DETAIL ERROR] {e}")
            QMessageBox.critical(self, "Error", str(e))

    def start_background_check(self):
        threading.Thread(target=background_check, daemon=True).start()

    # def rack_notify_telegram(self):
    #     if self.filtered_df is None:
    #         return
    
    #     import requests
    #     import re
    
    #     BOT_TOKEN = "8663778811:AAEqvTZYh8Lx6PocVh6zEVCEtF9I59VGdIo"
    #     CHAT_ID = "-5117824741"
    
    #     selected_racks = []
    
    #     for i in range(self.rack_list.count()):
    #         item = self.rack_list.item(i)
    #         if item.data(Qt.CheckStateRole) == Qt.Checked:
    #             rack = item.text().split(" (")[0]
    #             selected_racks.append(rack)
    
    #     if not selected_racks:
    #         QMessageBox.warning(self, "No Selection", "Select at least one rack")
    #         return

    # # 🔥 SORT
    #     def rack_sort_key(x):
    #         nums = re.findall(r'\d+', str(x))
    #         return int(nums[0]) if nums else 0

    #     selected_racks = sorted(selected_racks, key=rack_sort_key)

    # # 🔥 BUILD MESSAGE (CLEAN FORMAT)
    #     lines = []
    #     for rack in selected_racks:
    #         df = self.filtered_df[
    #             self.filtered_df["Current Rack Grp"] == rack
    #         ]

    #         trays = df["Tray Code"].drop_duplicates().astype(str).tolist()

    #         if trays:
    #             line = f"{rack}  " + "  ".join(trays)
    #             lines.append(line)

    #     message = "\n".join(lines)

    #     url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    #     try:
    #         requests.post(url, data={
    #             "chat_id": CHAT_ID,
    #             "text": message
    #         })
    #         QMessageBox.information(self, "Sent", "Message sent to Telegram group")
    #     except Exception as e:
    #         QMessageBox.critical(self, "Error", str(e))

    def apply_light(self):
        self.setStyleSheet("QWidget { background:#f5f5f5; color:#111; }")

    def toggle_theme(self):
        if self.dark:
            self.apply_light()
        else:
            self.apply_dark()
        self.dark = not self.dark

    # =========================
    # FILTERS
    # =========================
    def apply_filters(self):
        if self.df is None:
            return

        self.active_rack_label.setText("All Racks")

        df = self.df.copy()
        df = self.remove_completed_trays(df)

        if self.filters["order_type"]:
            df = df[df["Order Type"].isin(self.filters["order_type"])]
        if self.filters["route_type"]:
            df = df[df["Route Type"].isin(self.filters["route_type"])]
        if self.filters["slot"]:
            df = df[df["Routetype"].isin(self.filters["slot"])]
        if self.filters["order_class"]:
            df = df[df["Order Class"].isin(self.filters["order_class"])]

        if self.search.text():
            df = df[df["Tray Code"].astype(str).str.contains(self.search.text(), case=False, na=False)]

        if self.remove_st.isChecked():
            df = df[df["Tray Code"].notna() & (df["Tray Code"] != "")]

        #  REMOVE NON PTL
        if self.remove_non_ptl.isChecked():
            if "Pick Type" in df.columns:
                df = df[df["Pick Type"].astype(str).str.upper() == "PTL"]

        if "Order Count" in self.df.columns:
            df = df.copy()

            if "Tray Code" in df.columns:
                df["Tray Code"] = df["Tray Code"].astype(str)

            if hasattr(self, "tray_counts"):
                df["Order Count"] = (
                    df["Tray Code"]
                    .map(self.tray_counts)
                    .fillna(1)
                    .astype(int)
                )
            else:
                df["Order Count"] = 1
        else:
            df["Order Count"] = 1

        df = df[[c for c in DISPLAY_COLUMNS if c in df.columns]]

        if "Tray Code" in df.columns:
            df = df.drop_duplicates(subset=["Tray Code"])


        self.filtered_df = df

        #  GET ALERT DATA
        alert_rows, alert_trays = self.get_highway_alert_rows()

        #  SET TABLE MODEL
        model = PandasModel(df, alert_rows)
        self.table.setModel(model)

        #  UPDATE BANNER (PLACE HERE)
        if alert_trays:
            tray_text = ", ".join(alert_trays[:10])
            extra = f" (+{len(alert_trays)-10})" if len(alert_trays) > 10 else ""

            self.alert_banner.setText(f"HIGHWAY ALERT: {tray_text}{extra}")
            self.alert_banner.setVisible(True)
        else:
            self.alert_banner.setVisible(False)

        # ? CONTROL FLASH TIMER (PLACE HERE)
        if alert_rows:
            if not self.flash_timer.isActive():
                self.flash_timer.start(120)  # smooth pulse
        else:
            self.flash_timer.stop()

        #  CONTINUE NORMAL FLOW
        self.update_rack(df)
        self.update_metrics(df)

    def update_rack(self, df):
        grp = df.groupby("Current Rack Grp").size()

        import re

        def rack_sort_key(r):
            if str(r).upper() == "HW":
                return (999, "Z")  # always last

            match = re.match(r"(\d+)([A-Z]?)", str(r))
            if match:
                num = int(match.group(1))
                letter = match.group(2) or ""
                return (num, letter)

            return (999, str(r))

        grp = grp.sort_index(key=lambda x: [rack_sort_key(i) for i in x])

        self.rack_list.blockSignals(True)
        self.rack_list.clear()

        for k, v in grp.items():
            item = QListWidgetItem(f"{k} ({v})")
            item.setData(Qt.CheckStateRole, Qt.Unchecked)

            # Bigger row height (card feel)
            item.setSizeHint(QSize(0, 40))

            self.rack_list.addItem(item)

        self.rack_list.blockSignals(False)

    def filter_rack(self):
        checked_racks = []

        for i in range(self.rack_list.count()):
            item = self.rack_list.item(i)
            if item.data(Qt.CheckStateRole) == Qt.Checked:
                rack = item.text().split(" (")[0]
                checked_racks.append(rack)

        if not checked_racks:
            self.table.setModel(PandasModel(self.filtered_df))
            self.active_rack_label.setText("All Racks")
            return

        df = self.filtered_df[
            self.filtered_df["Current Rack Grp"].isin(checked_racks)
        ]

        self.active_rack_label.setText(
            f"Active Racks: {', '.join(checked_racks[:3])}" +
            (f" (+{len(checked_racks)-3})" if len(checked_racks) > 3 else "")
        )

        alert_rows, alert_trays = self.get_highway_alert_rows()

        model = PandasModel(df, alert_rows)
        self.table.setModel(model)

        #  UPDATE BANNER
        if alert_trays:
            tray_text = ", ".join(alert_trays[:10])
            extra = f" (+{len(alert_trays)-10})" if len(alert_trays) > 10 else ""

            self.alert_banner.setText(f" HIGHWAY ALERT: {tray_text}{extra}")
            self.alert_banner.setVisible(True)
        else:
            self.alert_banner.setVisible(False)
    # =========================
    # EXPORT
    # =========================
    def export_view(self):
        from datetime import datetime

        count = len(self.filtered_df)
        default_name = f"filtered_{count}_rows_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save",
            default_name,   # 🔥 auto filename here
            "Excel (*.xlsx)"
        )

        if not path:
            return

        df = self.filtered_df.copy()

        if hasattr(self, "tray_counts"):
            df["Order Count"] = df["Tray Code"].map(self.tray_counts).fillna(1).astype(int)
        else:
            df["Order Count"] = 1

        if "Tray Code" in df.columns:
            df = df.drop_duplicates(subset=["Tray Code"])

        df.to_excel(path, index=False)

    def export_rack(self):
        default_name = f"rack_report_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save",
            default_name,   # 🔥 auto filename
            "Excel (*.xlsx)"
        )

        if not path:
            return

        import re

        def rack_sort_key(x):
            nums = re.findall(r'\d+', str(x))
            return int(nums[0]) if nums else 0

        racks = sorted(
            self.filtered_df["Current Rack Grp"].dropna().unique(),
            key=rack_sort_key
        )

        data = []

        for r in racks:
            trays = self.filtered_df[
                self.filtered_df["Current Rack Grp"] == r
            ]["Tray Code"].drop_duplicates().astype(str).tolist()

            if trays:
                row = {"Rack": r}

                # 🔥 Spread trays across columns
                for i, tray in enumerate(trays, start=1):
                    row[f"Tray{i}"] = tray

                data.append(row)

        final_df = pd.DataFrame(data)

        # 🔥 Fill missing cells (important for clean Excel)
        final_df = final_df.fillna("")

        final_df.to_excel(path, index=False)

    def select_all_racks(self):
        self.rack_list.blockSignals(True)
        for i in range(self.rack_list.count()):
            item = self.rack_list.item(i)
            item.setData(Qt.CheckStateRole, Qt.Checked)
        self.rack_list.blockSignals(False)
        self.filter_rack()
    
    
    def clear_all_racks(self):
        self.rack_list.blockSignals(True)
        for i in range(self.rack_list.count()):
            item = self.rack_list.item(i)
            item.setData(Qt.CheckStateRole, Qt.Unchecked)
        self.rack_list.blockSignals(False)
        self.filter_rack()

    def print_selected_racks(self):
        if self.filtered_df is None:
            return

        selected_racks = []

        for i in range(self.rack_list.count()):
            item = self.rack_list.item(i)
            if item.data(Qt.CheckStateRole) == Qt.Checked:
                rack = item.text().split(" (")[0]
                selected_racks.append(rack)

        if not selected_racks:
            QMessageBox.warning(self, "No Selection", "Select at least one rack")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Print File", "", "Excel (*.xlsx)"
        )

        if not path:
            return

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for rack in selected_racks:
                df = self.filtered_df[
                    self.filtered_df["Current Rack Grp"] == rack
                ]

                if "Tray Code" in df.columns:
                    df = df.drop_duplicates(subset=["Tray Code"])

                df.to_excel(writer, sheet_name=str(rack)[:30], index=False)

        QMessageBox.information(self, "Done", "Rack print file created")

    def print_selected_racks_pdf(self):
        if self.filtered_df is None:
            return

        import getpass
        from datetime import datetime

        selected_racks = []

        for i in range(self.rack_list.count()):
            item = self.rack_list.item(i)
            if item.data(Qt.CheckStateRole) == Qt.Checked:
                rack = item.text().split(" (")[0]
                selected_racks.append(rack)

        if not selected_racks:
            QMessageBox.warning(self, "No Selection", "Select at least one rack")
            return

        username = getpass.getuser()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 🔥 BUILD HTML
        html = f"""
        <html>
        <head>
        <style>
            body {{ font-family: Segoe UI; font-size: 9pt; margin: 5px; }}

            h1 {{ color: #58a6ff; margin-bottom: 5px; }}
            h2 {{ color: #238636; margin: 2px 0; font-size: 10pt; }}

            .meta {{
                margin-bottom: 5px;
                font-size: 8pt;
                color: #555;
            }}

            table {{
                border-collapse: collapse;
                width: 100%;
                margin-bottom: 5px;
            }}

            td {{
                padding: 3px;
                border: 1px solid #ccc;
                font-size: 8pt;
            }}

            .b2b {{ background-color: #e3f2fd; }}
            .b2c {{ background-color: #fff3cd; }}
        </style>
        </head>
        <body>


        <h5>Rack Report</h5>

        <div class="meta">
            Generated by: {username} <br>
            Generated on: {timestamp} <br>
            Total Racks: {len(selected_racks)}
        </div>
        """

        for rack in selected_racks:
            df = self.filtered_df[
                self.filtered_df["Current Rack Grp"] == rack
            ]

            # 🔥 LIMIT TO REQUIRED COLUMNS ONLY
            df = df[[c for c in DISPLAY_COLUMNS if c in df.columns]]

            if "Tray Code" in df.columns:
                df = df.drop_duplicates(subset=["Tray Code"])

            html += f"<h6>Rack: {rack}</h6>"
            html += "<table>"

            # Rows with conditional coloring
            for _, row in df.iterrows():
                order_type = str(row.get("Order Type", "")).upper()

                row_class = ""
                if "B2B" in order_type:
                    row_class = "b2b"
                elif "B2C" in order_type:
                    row_class = "b2c"

                html += f"<tr class='{row_class}'>"

                for val in row:
                    html += f"<td>{str(val)}</td>"

                html += "</tr>"

            html += "</table>"

        html += "</body></html>"

        # 🔥 CREATE DOCUMENT
        doc = QTextDocument()
        doc.setHtml(html)

        # 🔥 AUTO PDF SAVE
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName("rack_report.pdf")

        doc.print_(printer)

        # 🔥 OPEN PRINT DIALOG (OPTIONAL)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QPrintDialog.Accepted:
            doc.print_(printer)

        QMessageBox.information(self, "Done", "PDF created + print ready")

    def change_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Data Folder")

        if not folder:
            return

        # Save to config
        self.config["data_folder"] = folder
        self.save_json(CONFIG_FILE, self.config)

        # Reload files immediately
        self.load_files()

    # =========================
    # FILES
    # =========================
    def load_files(self):
        folder = self.config.get("data_folder")

        if not folder or not os.path.exists(folder):
            folder = QFileDialog.getExistingDirectory(self, "Select Folder")
            if not folder:
                return

            self.config["data_folder"] = folder
            self.save_json(CONFIG_FILE, self.config)

        self.folder = folder
        self.manage_file_archive()

        files = [
    f for f in os.listdir(folder)
    if (
        f.lower().endswith(".xlsx")
        and "tray_status" in f.lower()
        and not f.startswith("~$")
    )
]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(folder, x)), reverse=True)

        self.file_box.clear()
        self.file_box.addItems(files)

        if files:
            self.file_box.setCurrentIndex(0)

    def load_file(self):
        file = self.file_box.currentText()

        if not file:
            return

        path = os.path.join(self.folder, file)

        if "~$" in path:
            self.log("[SKIP] Temp file detected")
            return

        # =========================
        # READ EXCEL SAFELY
        # =========================
        for _ in range(5):
            try:
                raw_df = pd.read_excel(path, header=2)
                self.raw_df = raw_df
                break
            except PermissionError:
                self.wait_non_blocking(1)
        else:
            self.log("[ERROR] File still locked")
            return

        temp_df = raw_df.copy()

        # Apply ONLY header fix (NOT process_df)
        temp_df.columns = temp_df.iloc[0]
        temp_df = temp_df[1:].reset_index(drop=True)
        temp_df.columns = temp_df.columns.astype(str).str.strip()
        
        # =========================
        # 🔍 FIND REQUIRED COLUMNS
        # =========================
        tray_col = None
        order_col = None
        
        for c in temp_df.columns:
            c_low = c.lower().replace(" ", "")
        
            if c_low == "traycode":
                tray_col = c
        
            if c_low == "orderid":
                order_col = c
        
        # DEBUG
        self.log(f"[DEBUG] tray_col: {tray_col}")
        self.log(f"[DEBUG] order_col: {order_col}")
        
        # =========================
        # 🔥 STEP 2: COUNT BEFORE DEDUPE
        # =========================
        if tray_col and order_col:
        
            temp_df[tray_col] = temp_df[tray_col].astype(str)
        
            tray_counts = (
                temp_df.groupby(tray_col)[order_col]
                .nunique()
                .to_dict()
            )
        
            self.tray_counts = tray_counts
            self.log(f"[OK] Tray counts computed (RAW): {len(tray_counts)}")
        
        else:
            self.tray_counts = {}
            self.log("[FAIL] Tray Code / Orderid not found")
        
        # =========================
        # 🔥 STEP 3: PROCESS DATA FOR UI
        # =========================
        df = process_df(raw_df)

        # =========================
        # 🔥 STEP 4: MAP BACK ORDER COUNT
        # =========================
        if "Tray Code" in df.columns:
            df["Tray Code"] = df["Tray Code"].astype(str)

            if hasattr(self, "tray_counts"):
                df["Order Count"] = df["Tray Code"].map(self.tray_counts).fillna(1).astype(int)
            else:
                df["Order Count"] = 1
        else:
            df["Order Count"] = 1

        # =========================
        # SAVE + REFRESH UI
        # =========================
        self.df = df
        self.base_df = df.copy()
        self.new_excel_loaded = True

        self.log(f"[COUNT LOADED] trays with counts: {len(self.tray_counts)}")

        self.populate_filters()
        self.apply_filters()

    def update_metrics(self, df):
        total = len(self.df) if self.df is not None else 0
        filtered = len(df)
        racks = df["Current Rack Grp"].nunique() if "Current Rack Grp" in df.columns else 0

        self.total_label.setText(f"Total: {total}")
        self.filtered_label.setText(f"Filtered: {filtered}")
        self.rack_count_label.setText(f"Racks: {racks}")

    def update_license_status(self):
        ok, msg, lic = validate_license()
    
        if not ok:
            self.license_label.setText(f"License: ❌ {msg}")
            self.license_label.setStyleSheet("color:red; font-weight:bold;")
            return
    
        expiry = lic.get("expires", "N/A").split("T")[0]
    
        try:
            days_left = (datetime.fromisoformat(lic["expires"]) - datetime.now()).days
        except:
            days_left = 0
    
        if days_left <= 3:
            color = "#ff4d4d"
        elif days_left <= 10:
            color = "#f2cc60"
        else:
            color = "#3fb950"
    
        self.license_label.setStyleSheet(f"color:{color}; font-weight:bold;")
        self.license_label.setText(
            f"License: ✅ Active | Expires: {expiry} ({days_left} days)"
        )

    def auto_refresh(self):
        if not hasattr(self, "folder"):
            return
    
        files = [
            f for f in os.listdir(self.folder)
            if (
                f.lower().endswith(".xlsx")
                and "tray_status" in f.lower()
                and not f.startswith("~$")
            )
        ]
    
        if not files:
            return
    
        files.sort(key=lambda x: os.path.getmtime(os.path.join(self.folder, x)), reverse=True)
        latest = files[0]
    
        # 🔥 ALWAYS reload if new OR same (force)
        if getattr(self, "last_loaded_file", None) != latest:
            self.log(f"[NEW FILE] {latest}")
            self.last_loaded_file = latest
    
            # 🔥 FORCE refresh dropdown
            self.file_box.blockSignals(True)
            self.file_box.clear()
            self.file_box.addItems(files)
            self.file_box.setCurrentText(latest)
            self.file_box.blockSignals(False)
    
            self.load_file()

    def populate_filters(self):
        self.order.populate(self.df["Order Type"].dropna().unique(), self.filters["order_type"])
        self.route.populate(self.df["Route Type"].dropna().unique(), self.filters["route_type"])
        self.slot.populate(self.df["Routetype"].dropna().unique(), self.filters["slot"])
        self.cls.populate(self.df["Order Class"].dropna().unique(), self.filters["order_class"])

    # =========================
    # PRESETS
    # =========================
    def save_preset(self):
        name, ok = QInputDialog.getText(self, "Preset", "Preset Name")
        if not ok or not name:
            return

        # 🔥 GET FROM TIME
        from_time, ok1 = QInputDialog.getText(
            self, "From Time", "Enter From Time (HH:MM:SS)", text="00:00:00"
        )
        if not ok1:
            return
        
        # 🔥 ASK BUSINESS DAY LOGIC
        use_prev_day, ok3 = QInputDialog.getItem(
            self,
            "Business Date",
            "Use previous day before 9 AM?",
            ["Yes", "No"],
            0,
            False
        )
        
        if not ok3:
            return
        
        use_prev_day_flag = True if use_prev_day == "Yes" else False

        # 🔥 GET TO TIME
        to_time, ok2 = QInputDialog.getText(
            self, "To Time", "Enter To Time (HH:MM:SS)", text="23:59:59"
        )
        if not ok2:
            return

        preset_data = self.filters.copy()
        preset_data["from_time"] = from_time
        preset_data["to_time"] = to_time
        preset_data["use_prev_day_until_9"] = use_prev_day_flag

        self.presets[name] = preset_data
        self.save_json(PRESET_FILE, self.presets)

        if self.preset_box.findText(name) == -1:
            self.preset_box.addItem(name)

    def load_preset(self):
        name = self.preset_box.currentText()
        if name in self.presets:
            p = self.presets[name]

            self.filters["order_type"] = p.get("order_type") or p.get("order", [])
            self.filters["route_type"] = p.get("route_type") or p.get("route", [])
            self.filters["slot"] = p.get("slot", [])
            self.filters["order_class"] = p.get("order_class") or p.get("class", [])

            self.populate_filters()
            self.apply_filters()

    def remove_completed_trays(self, df):
        if "Tray Code" not in df.columns or "Tray Completed Time" not in df.columns:
            return df

        grouped = df.groupby("Tray Code")
        keep_trays = []

        for tray, group in grouped:
            if group["Tray Completed Time"].isna().any():
                keep_trays.append(tray)

        return df[df["Tray Code"].isin(keep_trays)]

    def run_all_presets(self):
        import time
        import subprocess

        if not hasattr(self, "last_run"):
            self.last_run = {}

        self.log("[START] Running all presets...")

        now = get_shift_now()
        self.log(f"Shift Time: {now}")

        # =========================
        #  COLLECT UNIQUE DATES
        # =========================
        date_to_presets = {}

        for name, preset in self.presets.items():
            business_date = get_business_date(preset)
            date_str = business_date.strftime("%Y-%m-%d")

            if date_str not in date_to_presets:
                date_to_presets[date_str] = []

            date_to_presets[date_str].append((name, preset))

        self.log(f"[DATES] {list(date_to_presets.keys())}")

        # =========================
        #  DOWNLOAD EACH DATE ONCE
        # =========================
        for date_str, preset_list in date_to_presets.items():

            self.log(f"[DOWNLOAD] {date_str}")

            success = False

            for attempt in range(3):
                try:
                    playm_path = os.path.join(os.getcwd(), "playm.exe")
                    process = subprocess.Popen([playm_path, date_str])
                    
                    while process.poll() is None:
                        self.wait_non_blocking(0.5)

                    if process.returncode == 0:
                        success = True
                        self.log(f"[OK] Download success {date_str}")
                        break
                    else:
                        self.log(f"[RETRY {attempt+1}] {date_str}")

                except Exception as e:
                    self.log(f"[ERROR] {date_str}: {e}")
                    self.wait_non_blocking(5)

            if not success:
                self.log(f"[FAIL] {date_str}")
                continue

            # =========================
            # LOAD FILE ONCE
            # =========================
            self.wait_non_blocking(5)
            self.load_files()
            self.load_file()

            # =========================
            # RUN PRESETS USING THIS DATA
            # =========================
            for name, preset in preset_list:

                now_ts = time.time()

                if name in self.last_run and now_ts - self.last_run[name] < 120:
                    self.log(f"[SKIP DUPLICATE] {name}")
                    continue

                self.last_run[name] = now_ts

                # =========================
                # TIME FILTER
                # =========================
                from_time = preset.get("from_time", "00:00:00")
                to_time = preset.get("to_time", "23:59:59")

                ft = datetime.strptime(from_time, "%H:%M:%S").time()
                tt = datetime.strptime(to_time, "%H:%M:%S").time()

                if ft <= tt:
                    valid = ft <= now <= tt
                else:
                    valid = now >= ft or now <= tt

                if not valid:
                    self.log(f"[SKIP] {name} (time)")
                    continue

                self.log(f"[RUN] {name}")

                # =========================
                # APPLY FILTERS
                # =========================
                self.filters["order_type"] = preset.get("order_type", [])
                self.filters["route_type"] = preset.get("route_type", [])
                self.filters["slot"] = preset.get("slot", [])
                self.filters["order_class"] = preset.get("order_class", [])

                self.populate_filters()
                self.apply_filters()

                QApplication.processEvents()
                self.wait_non_blocking(1)

                if self.filtered_df is None or self.filtered_df.empty:
                    self.log(f"[SKIP] {name} empty")
                    continue

                self.realtime_update()

                # =========================
                # WAIT
                # =========================
                self.log("[WAIT] 2 min")
                self.wait_non_blocking(120)

        self.log("[DONE] All presets completed")


    def get_highway_alert_rows(self):
       if self.filtered_df is None:
           return set(), []

       df = self.filtered_df.reset_index(drop=True)

       highway_mask = df["Current Rack Grp"].astype(str).str.upper() == "HW"

       alert_rows = set()
       alert_trays = []

       count = 0

       for i in range(len(df)-1, -1, -1):
           if highway_mask.iloc[i]:
               count += 1
               alert_rows.add(i)
               alert_trays.append(str(df.iloc[i]["Tray Code"]))

               if count >= 7:
                   return alert_rows, list(reversed(alert_trays))
           else:
               break

       return set(), []
    
    def flash_alert_rows(self):
        model = self.table.model()
        if hasattr(model, "toggle_flash"):
            model.toggle_flash()
    

    def send_preset_to_telegram(self, preset_name, preset):
        import requests

        BOT_TOKEN = "8663778811:AAEqvTZYh8Lx6PocVh6zEVCEtF9I59VGdIo"
        CHAT_ID = "-5070624209"

        slot = ", ".join(self.filters.get("slot", [])) or "All"
        order_type = ", ".join(self.filters.get("order_type", [])) or "All"
        route_type = ", ".join(self.filters.get("route_type", [])) or "All"

        from_time = preset.get("from_time", "00:00:00")
        to_time = preset.get("to_time", "23:59:59")

        # 🔥 HEADER
        lines = [
            f"📦 {preset_name}",
            f"🕒 {from_time} → {to_time}",
            f"📍 Slot: {slot}",
            f"📦 Order: {order_type}",
            f"🚚 Route: {route_type}",
            ""
        ]

        #  COUNT TRAYS IN HIGHWAY
        highway_df = self.filtered_df[
            self.filtered_df["Current Rack Grp"] == "Highway"
        ]

        tray_counts = highway_df["Tray Code"].value_counts()

        # trays that appear >7 times
        highway_alert_trays = set(
            tray_counts[tray_counts > 7].index.astype(str)
        )

        racks = self.filtered_df.groupby("Current Rack Grp")

        for rack, df in racks:
            trays = df["Tray Code"].astype(str).tolist()  # ? DO NOT drop duplicates

            formatted_trays = []

            for t in trays:
                if rack == "Highway" and t in highway_alert_trays:
                    formatted_trays.append(f"{t}")  #  MARK RED
                else:
                    formatted_trays.append(t)

            if formatted_trays:
                lines.append(f"{rack}  " + "  ".join(formatted_trays))

        message = "\n".join(lines)

        telegram_engine.send_new(preset_name, message)

    def realtime_update(self):
        import hashlib

        # =========================
        # 1. FETCH DB DATA
        # =========================
        data = get_filtered_data()

        if not data or self.df is None:
            return

        # =========================
        # 2. BUILD DB TRAY → RACK MAP
        # =========================
        tray_to_rack = {}

        for row in data:

            tray = str(row.get("Tray Code", "")).strip()
            rack = str(row.get("Current Rack Grp", "")).strip()

            if not tray:
                continue

            # 🚫 skip rack >= 42
            if rack:
                try:
                    num = int(''.join(filter(str.isdigit, rack)))
                    if num >= 42:
                        continue
                except:
                    pass

            # 🚫 skip lane 16
            if str(row.get("Lane", "")).strip() == "16":
                continue

            tray_to_rack[tray] = rack

        # =========================
        # 3. UPDATE MAIN DF RACKS
        # =========================
        if (
            "Tray Code" not in self.df.columns or
            "Current Rack Grp" not in self.df.columns
        ):
            return


        self.df = self.base_df.copy()

        self.df["Tray Code"] = (
            self.df["Tray Code"]
            .astype(str)
        )

        updated_racks = self.df["Tray Code"].map(tray_to_rack)

        self.df["Current Rack Grp"] = (
            updated_racks
            .fillna(self.df["Current Rack Grp"])
            .fillna("HW")
        )

        # normalize
        self.df["Current Rack Grp"] = (
            self.df["Current Rack Grp"]
            .astype(str)
            .replace("-", "HW")
            .replace("Highway", "HW")
            .replace("nan", "HW")
        )

        # =========================
        # 4. REFRESH UI
        # =========================
        self.apply_filters()

        if self.filtered_df is None or self.filtered_df.empty:
            return

        # =========================
        # 5. INIT GLOBAL STATE
        # =========================
        if not hasattr(self, "prev_tray_map"):
            self.prev_tray_map = {}

        # =========================
        # 6. PROCESS EACH PRESET
        # =========================
        for preset_name, preset in self.presets.items():

            # 🔥 isolated state per preset
            preset_prev_map = self.prev_tray_map.setdefault(
                preset_name,
                {}
            )

            # =========================
            # APPLY PRESET FILTER
            # =========================
            preset_df = self.apply_preset_filter_df(
                self.df,
                preset
            )

            preset_df = self.remove_completed_trays(preset_df)

            if preset_df.empty:
                continue

            preset_df = preset_df.copy()

            # =========================
            # ORDER COUNT MAP
            # =========================
            if "Tray Code" in preset_df.columns:

                preset_df["Tray Code"] = (
                    preset_df["Tray Code"]
                    .astype(str)
                )

            if hasattr(self, "tray_counts"):

                preset_df["Order Count"] = (
                    preset_df["Tray Code"]
                    .map(self.tray_counts)
                    .fillna(1)
                    .astype(int)
                )

            else:
                preset_df["Order Count"] = 1

            # =========================
            # BUILD CURRENT STATE
            # =========================
            current_tray_map = {}

            for _, row in preset_df.iterrows():

                tray = str(row["Tray Code"]).strip()
                rack = str(row["Current Rack Grp"]).strip()

                current_tray_map[tray] = rack

            # =========================
            # MOVEMENT DETECTION
            # =========================
            changed = False

            for tray, rack in current_tray_map.items():

                prev_rack = preset_prev_map.get(tray)

                if prev_rack and prev_rack != rack:
                    changed = True
                    break

            # =========================
            # SLOT INFO
            # =========================
            slots = []

            if "Routetype" in preset_df.columns:

                slots = (
                    preset_df["Routetype"]
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                )

            # =========================
            # BUILD RACK MAP
            # =========================
            rack_map = telegram_engine.build_rack_map(
                preset_df
            )

            rack_map["__slots__"] = slots

            # =========================
            # BUILD TELEGRAM MESSAGE
            # =========================
            valid_racks = {
                k: v
                for k, v in rack_map.items()
                if not str(k).startswith("__") and v
            }

            if not valid_racks:
                continue
            message = telegram_engine.build_message(
                preset_name,
                rack_map,
                edited=changed
            )

            current_hash = hashlib.md5(
                message.encode()
            ).hexdigest()

            last_key = f"{preset_name}_hash"

            # =========================
            # SKIP IF NO CHANGE
            # =========================
            if getattr(self, last_key, None) == current_hash:
                continue

            # =========================
            # TELEGRAM MESSAGE ID
            # =========================
            msg_id = telegram_engine.get_message_id(
                preset_name
            )

            # =====================================
            # NEW EXCEL FILE
            # SEND NEW TELEGRAM MESSAGE
            # =====================================
            if getattr(self, "new_excel_loaded", False):

                first_message = telegram_engine.build_message(
                    preset_name,
                    rack_map,
                    edited=False
                )
            
                new_id = telegram_engine.send_new(
                    first_message,
                    preset_name=preset_name
                )
            
                if new_id:
                
                    telegram_engine.save_message_id(
                        preset_name,
                        new_id
                    )
            
                # ✅ IMPORTANT
                # future updates should edit only
                setattr(self, f"{preset_name}_hash", current_hash)
            
                preset_prev_map.clear()
                preset_prev_map.update(current_tray_map)
            
                continue
            
            # =====================================
            # DB REALTIME UPDATE
            # EDIT EXISTING MESSAGE
            # =====================================
            elif msg_id:

                telegram_engine.edit(
                    msg_id,
                    message
                )
            
            else:
            
                new_id = telegram_engine.send_new(
                    message,
                    preset_name=preset_name
                )
            
                if new_id:
                    telegram_engine.save_message_id(
                        preset_name,
                        new_id
                    )

            # =========================
            # SAVE HASH
            # =========================
            setattr(
                self,
                last_key,
                current_hash
            )

            # =========================
            # SAVE CLEAN STATE
            # =========================
            preset_prev_map.clear()
            preset_prev_map.update(current_tray_map)

            self.log(
                f"[TELEGRAM UPDATED] {preset_name}"
            )

        self.new_excel_loaded = False



    def manage_file_archive(self):
        import shutil
        import os
        from datetime import datetime, timedelta

        if not hasattr(self, "folder"):
            return

        # 1. Grab only valid tray_status files
        files = [
            f for f in os.listdir(self.folder)
            if (
                f.lower().endswith(".xlsx")
                and "tray_status" in f.lower()
                and not f.startswith("~$")
            )
        ]

        if len(files) <= 10:
            return  # Nothing to archive yet

        # 2. Sort by oldest first based on modification time
        files.sort(key=lambda x: os.path.getmtime(os.path.join(self.folder, x)))

        # 3. Identify the excess oldest files (keep exactly the latest 10)
        files_to_move = files[:-10]

        archive_base = os.path.join(self.folder, "archive")

        for f in files_to_move:
            src = os.path.join(self.folder, f)
            
            # 🔥 Get the time the file was ACTUALLY created/downloaded
            file_timestamp = os.path.getmtime(src)
            file_time = datetime.fromtimestamp(file_timestamp)
            
            # 🔥 Apply the 9 AM Business Date Logic to the file's time
            if file_time.hour < 9:
                file_biz_date = file_time - timedelta(days=1)
            else:
                file_biz_date = file_time
                
            archive_date_str = file_biz_date.strftime("%Y-%m-%d")
            archive_folder = os.path.join(archive_base, archive_date_str)
            
            # Ensure the daily folder exists
            os.makedirs(archive_folder, exist_ok=True)
            
            dst = os.path.join(archive_folder, f)

            # Move it!
            try:
                shutil.move(src, dst)
                self.log(f"[ARCHIVE] Moved {f} -> archive/{archive_date_str}")
            except Exception as e:
                self.log(f"[ARCHIVE ERROR] {f}: {e}")

    # =========================
    # JSON
    # =========================
    def load_json(self, p):
        return json.load(open(p)) if os.path.exists(p) else {}

    def save_json(self, p, d):
        json.dump(d, open(p, "w"), indent=4)

# =========================
# START
# =========================
if __name__ == "__main__":
    ok, msg, _ = validate_license()
    if not ok:
        app = QApplication(sys.argv)
        QMessageBox.critical(None, "License Error", msg)
        sys.exit()

    app = QApplication(sys.argv)

    win = App()
    win.show()

    # ✅ run AFTER window exists
    QTimer.singleShot(5000, win.start_background_check)

    sys.exit(app.exec())