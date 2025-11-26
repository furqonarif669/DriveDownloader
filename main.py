import sys
import os
import re
import json
import subprocess
import requests
import platform
import zipfile
import shutil
import struct
import socket
from time import sleep

from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                               QLineEdit, QPushButton, QFileDialog, QListWidget, 
                               QListWidgetItem, QProgressBar, QLabel, QHBoxLayout, 
                               QMessageBox, QFrame, QGraphicsDropShadowEffect,
                               QSizePolicy)
from PySide6.QtCore import QThread, Signal, Qt, QSize, QTimer
from PySide6.QtGui import QColor

# --- 0. DARK MODE STYLESHEET ---
DARK_THEME = """
QMainWindow { background-color: #121212; }
QWidget { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 13px; color: #e0e0e0; }
QLineEdit { padding: 10px; border: 1px solid #333; border-radius: 6px; background-color: #252525; color: #ffffff; min-height: 24px; }
QLineEdit:focus { border: 1px solid #0d6efd; background-color: #333; }
QLineEdit:disabled { background-color: #1a1a1a; color: #555; border: 1px solid #222; }
QPushButton { border-radius: 6px; border: 1px solid #444; background-color: #3a3a3a; color: white; font-weight: 600; padding: 0px 16px; }
QPushButton:hover { background-color: #4a4a4a; border-color: #666; }
QPushButton:pressed { background-color: #222; }
QPushButton:disabled { background-color: #1f1f1f; color: #444; border: 1px solid #2a2a2a; }
QPushButton#PrimaryBtn { background-color: #0d6efd; border: 1px solid #0d6efd; color: white; }
QPushButton#PrimaryBtn:hover { background-color: #0b5ed7; }
QPushButton#PrimaryBtn:disabled { background-color: #1f1f1f; border: 1px solid #2a2a2a; color: #444; }
QFrame#DashboardCard QPushButton { background-color: #444; border: 1px solid #555; color: white; }
QFrame#DashboardCard QPushButton:hover { background-color: #555; border-color: #777; }
QFrame#DashboardCard QPushButton:disabled { background-color: #2a2a2a; border: 1px solid #333; color: #555; }
QFrame#DashboardCard QPushButton#DangerBtn { background-color: transparent; border: 1px solid #d32f2f; color: #ff6b6b; }
QFrame#DashboardCard QPushButton#DangerBtn:hover { background-color: #d32f2f; color: white; }
QListWidget { background-color: transparent; border: none; }
QListWidget::item { background-color: transparent; margin-bottom: 16px; }
QListWidget::item:selected { background-color: transparent; }
QFrame#DashboardCard { background-color: #1e1e1e; border-radius: 12px; border: 1px solid #333; }
QProgressBar { border: none; background-color: #2c2c2c; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background-color: #0d6efd; border-radius: 4px; }
"""

# --- 1. PORTABILITY & PATH HELPERS ---

def get_app_root():
    """Determines correct root for data/binaries on all platforms."""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        # Fix for macOS App Bundle pathing
        if platform.system() == "Darwin" and ".app/Contents/MacOS" in base:
            # Move up 3 levels to sit next to the .app file
            base = os.path.abspath(os.path.join(base, "../../.."))
        return base
    else:
        return os.path.dirname(os.path.abspath(__file__))

class RcloneManager:
    BASE_URL = "https://downloads.rclone.org/rclone-current-{os}-{arch}.zip"
    
    @staticmethod
    def get_platform_details():
        system = platform.system().lower()
        machine = platform.machine().lower()
        if 'windows' in system:
            return 'windows', 'rclone.exe'
        elif 'darwin' in system:
            return 'osx', 'rclone'
        else:
            return 'linux', 'rclone'

    @staticmethod
    def get_binaries_dir():
        base = get_app_root()
        path = os.path.join(base, "binaries")
        if not os.path.exists(path):
            try: os.makedirs(path, exist_ok=True)
            except: pass
        return path

def get_rclone_path():
    bin_dir = RcloneManager.get_binaries_dir()
    system = platform.system().lower()
    bin_name = "rclone.exe" if "windows" in system else "rclone"
    return os.path.join(bin_dir, bin_name)

def get_rclone_config_path():
    base = get_app_root()
    return os.path.join(base, "rclone.conf")

# --- 2. FORMATTING HELPERS ---

def format_bytes(size):
    if not size: return "0 B"
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"

def format_time(seconds):
    if seconds is None: return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"

# --- 3. LOGIC MODULES ---

class DriveLinkParser:
    @staticmethod
    def get_id(user_input):
        url = user_input.strip()
        if re.match(r'^[a-zA-Z0-9_-]+$', url): return url
        try:
            if not url.startswith('http'): url = 'https://' + url
            response = requests.head(url, allow_redirects=True, timeout=5)
            resolved_url = response.url
        except: resolved_url = url
        patterns = [r'folders/([a-zA-Z0-9_-]+)', r'/d/([a-zA-Z0-9_-]+)', r'[?&]id=([a-zA-Z0-9_-]+)']
        for pattern in patterns:
            match = re.search(pattern, resolved_url)
            if match: return match.group(1)
        return None

# --- 4. THREADS ---

class NetworkMonitor(QThread):
    connection_changed = Signal(bool)
    def __init__(self):
        super().__init__()
        self._is_running = True
    def run(self):
        last_status = None
        while self._is_running:
            is_online = self.check_connection()
            if is_online != last_status:
                self.connection_changed.emit(is_online)
                last_status = is_online
            for _ in range(6): 
                if not self._is_running: return
                self.msleep(500) 
    def stop(self): self._is_running = False
    def check_connection(self):
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return True
        except OSError:
            try:
                socket.create_connection(("1.1.1.1", 53), timeout=2)
                return True
            except OSError: return False

class RcloneInstallerThread(QThread):
    progress_signal = Signal(str)
    percent_signal = Signal(int)
    finished_signal = Signal(bool, str)
    def run(self):
        try:
            self.progress_signal.emit("Detecting System...")
            os_type, bin_name = RcloneManager.get_platform_details()
            
            machine = platform.machine().lower()
            is_64 = struct.calcsize("P") * 8 == 64
            if 'arm' in machine or 'aarch64' in machine: arch = 'arm64'
            elif is_64: arch = 'amd64'
            else: arch = '386'

            url = RcloneManager.BASE_URL.format(os=os_type, arch=arch)
            self.progress_signal.emit(f"Downloading Rclone ({arch})...")
            
            response = requests.get(url, stream=True)
            response.raise_for_status()
            total_length = response.headers.get('content-length')
            zip_path = os.path.join(RcloneManager.get_binaries_dir(), "temp.zip")
            
            with open(zip_path, 'wb') as f:
                if total_length is None: f.write(response.content)
                else:
                    dl = 0
                    total_length = int(total_length)
                    for chunk in response.iter_content(chunk_size=4096):
                        dl += len(chunk)
                        f.write(chunk)
                        done = int(50 * dl / total_length)
                        self.percent_signal.emit(done)
            
            self.progress_signal.emit("Extracting...")
            self.percent_signal.emit(75)
            bin_dir = RcloneManager.get_binaries_dir()
            final_bin_path = os.path.join(bin_dir, bin_name)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for file in zip_ref.namelist():
                    if file.endswith(bin_name):
                        source = zip_ref.open(file)
                        target = open(final_bin_path, "wb")
                        with source, target: shutil.copyfileobj(source, target)
                        break
            os.remove(zip_path)
            if platform.system() != "Windows": os.chmod(final_bin_path, 0o755)
            self.percent_signal.emit(100)
            self.finished_signal.emit(True, "Installed successfully!")
        except Exception as e: self.finished_signal.emit(False, str(e))

class DownloadWorker(QThread):
    progress_update = Signal(dict)
    finished = Signal()
    failed = Signal(str) 
    def __init__(self, rclone_path, folder_id, save_path, token=None):
        super().__init__()
        self.rclone_path = rclone_path
        self.folder_id = folder_id
        self.save_path = save_path
        self.token = token 
        self.process = None
        self.is_paused = False
    def run(self):
        self.is_paused = False 
        if not self.token:
            self.failed.emit("Login Required!")
            return
        cmd = [
            self.rclone_path, "copy", "--drive-root-folder-id", self.folder_id, 
            "ram_drive:", self.save_path, "--use-json-log", "--stats", "1s", "-v",
            "--inplace", "--ignore-checksum", "--metadata",
            "--transfers", "4", "--checkers", "4", "--drive-chunk-size", "64M", 
            "--buffer-size", "32M", "--timeout", "10m", "--contimeout", "10m", "--retries", "10"
        ]
        
        creation_flags = 0
        if platform.system() == "Windows":
            creation_flags = subprocess.CREATE_NO_WINDOW

        env = os.environ.copy()
        env["RCLONE_CONFIG_RAM_DRIVE_TYPE"] = "drive"
        env["RCLONE_CONFIG_RAM_DRIVE_TOKEN"] = self.token
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                text=True, bufsize=1, encoding='utf-8', errors='replace',
                creationflags=creation_flags, env=env 
            )
        except Exception as e:
            self.failed.emit(str(e))
            return
        while True:
            if self.is_paused:
                if self.process: self.process.kill()
                break
            line = self.process.stderr.readline()
            if not line and self.process.poll() is not None: break
            if line:
                match = re.search(r'\{.*\}', line.strip())
                if match:
                    try:
                        data = json.loads(match.group(0))
                        if 'stats' in data: self.progress_update.emit(data['stats'])
                    except: pass
        if not self.is_paused and self.process.poll() == 0: self.finished.emit()
        elif not self.is_paused: self.failed.emit("Error (Network/Auth)")
    def stop(self):
        self.is_paused = True
        if self.process: self.process.kill()
        self.wait()

# --- 5. GUI WIDGETS ---

class DownloadDashboard(QWidget):
    remove_requested = Signal() 
    def __init__(self, folder_id, save_path, worker, initial_size=0, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.save_path = save_path
        self.is_paused_state = False 
        self.known_total_size = initial_size 
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.card = QFrame()
        self.card.setObjectName("DashboardCard") 
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.card.setGraphicsEffect(shadow)
        card_layout = QVBoxLayout(self.card)
        card_layout.setSpacing(16) 
        card_layout.setContentsMargins(20, 20, 20, 30) 
        
        top = QHBoxLayout()
        self.lbl_title = QLabel(f"{folder_id}")
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 16px; color: #ffffff;")
        self.lbl_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.lbl_title.setMinimumWidth(50)
        self.lbl_status = QLabel("Initializing")
        self.lbl_status.setStyleSheet("background-color: #ffd700; color: black; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 11px; min-height: 18px;")
        self.lbl_status.setAlignment(Qt.AlignCenter) 
        self.lbl_status.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        top.addWidget(self.lbl_title)
        top.addSpacing(15) 
        top.addWidget(self.lbl_status)
        card_layout.addLayout(top)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        card_layout.addWidget(self.progress_bar)

        stats = QHBoxLayout()
        self.lbl_speed = QLabel("🚀 0 B/s")
        self.lbl_size = QLabel("📦 Waiting...")
        self.lbl_eta = QLabel("⏳ --:--")
        for lbl in [self.lbl_speed, self.lbl_size, self.lbl_eta]: lbl.setStyleSheet("color: #bbbbbb; font-size: 13px;")
        stats.addWidget(self.lbl_speed)
        stats.addStretch()
        stats.addWidget(self.lbl_size)
        stats.addStretch()
        stats.addWidget(self.lbl_eta)
        card_layout.addLayout(stats)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #444;")
        card_layout.addWidget(line)

        btm = QHBoxLayout()
        btm.setSpacing(12) 
        self.lbl_file = QLabel("Ready to start.")
        self.lbl_file.setStyleSheet("color: #888; font-size: 12px; font-style: italic;")
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setCursor(Qt.PointingHandCursor)
        self.btn_pause.setMinimumSize(90, 36)
        self.btn_open = QPushButton("Open")
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.setMinimumSize(90, 36)
        self.btn_open.setEnabled(True) 
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("DangerBtn")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setMinimumSize(90, 36)
        btm.addWidget(self.lbl_file, 1)
        btm.addWidget(self.btn_pause)
        btm.addWidget(self.btn_open)
        btm.addWidget(self.btn_delete)
        card_layout.addLayout(btm)
        self.main_layout.addWidget(self.card)

        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_open.clicked.connect(self.open_folder)
        self.btn_delete.clicked.connect(self.remove_requested.emit)
        self.worker.progress_update.connect(self.update_ui)
        self.worker.finished.connect(self.on_finish)
        self.worker.failed.connect(self.on_fail)

        if self.known_total_size > 0:
            final_fmt = format_bytes(self.known_total_size)
            self.lbl_size.setText(f"{format_bytes(0)} / {final_fmt}")
            self.lbl_status.setText("PAUSED")
            self.lbl_status.setStyleSheet("background-color: #555; color: white; border-radius: 6px; padding: 6px 12px; font-size: 11px; font-weight: bold;")
            self.is_paused_state = True
            self.btn_pause.setText("Resume")
            self.lbl_eta.setText("Paused")

    def set_session_active(self, active):
        is_finished = self.lbl_status.text() == "COMPLETED"
        if not active:
            self.btn_pause.setEnabled(False)
            self.btn_pause.setText("Login Req")
        else:
            self.btn_pause.setEnabled(not is_finished)
            if self.is_paused_state: self.btn_pause.setText("Resume")
            else: self.btn_pause.setText("Pause")

    def get_state(self):
        return {"id": self.worker.folder_id, "path": self.save_path, "total_size": self.known_total_size, "is_finished": self.lbl_status.text() == "COMPLETED"}

    def update_ui(self, stats):
        if self.is_paused_state: return
        self.lbl_status.setText("DOWNLOADING")
        self.lbl_status.setStyleSheet("background-color: #0d6efd; color: white; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 11px;")
        session_done = stats.get('bytes', 0)
        session_total = stats.get('totalBytes', stats.get('total_bytes', 0))
        speed_val = stats.get('speed', 0)
        eta_val = stats.get('eta', None)
        if session_total > self.known_total_size: self.known_total_size = session_total
        if self.known_total_size > 0:
            bytes_remaining = session_total - session_done
            estimated_done = self.known_total_size - bytes_remaining
            if estimated_done > self.known_total_size: estimated_done = self.known_total_size
            if estimated_done < 0: estimated_done = 0
            percent = int((estimated_done / self.known_total_size) * 100)
            self.progress_bar.setValue(percent)
            self.lbl_size.setText(f"{format_bytes(estimated_done)} / {format_bytes(self.known_total_size)}")
        else:
            self.progress_bar.setValue(0)
            self.lbl_size.setText(f"{format_bytes(session_done)} (Scanning...)")
        self.lbl_speed.setText(f"🚀 {format_bytes(speed_val)}/s")
        if eta_val is not None: self.lbl_eta.setText(f"⏳ {format_time(eta_val)}")
        if 'transferring' in stats and stats['transferring']:
            current_file = stats['transferring'][0].get('name', 'Unknown')
            if len(current_file) > 30: current_file = current_file[:27] + "..."
            self.lbl_file.setText(current_file)

    def on_finish(self):
        if self.is_paused_state: return
        self.progress_bar.setValue(100)
        self.lbl_status.setText("COMPLETED")
        self.lbl_status.setStyleSheet("background-color: #198754; color: white; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 11px;")
        self.lbl_speed.setText("🚀 Done")
        self.lbl_eta.setText("0s")
        if self.known_total_size > 0:
            final_fmt = format_bytes(self.known_total_size)
            self.lbl_size.setText(f"{final_fmt}")
        self.lbl_file.setText("Success")
        self.btn_open.setEnabled(True)
        self.btn_pause.setEnabled(False)

    def on_fail(self, msg):
        self.is_paused_state = True
        self.lbl_status.setText("ERROR")
        self.lbl_status.setStyleSheet("background-color: #dc3545; color: white; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 11px;")
        self.lbl_speed.setText("Offline")
        self.lbl_eta.setText("Error")
        self.btn_pause.setText("Retry")
        self.btn_pause.setEnabled(True)
        self.lbl_file.setText(str(msg)[:40])

    def toggle_pause(self):
        if self.is_paused_state:
            self.is_paused_state = False
            self.btn_pause.setText("Pause")
            self.lbl_status.setText("RESUMING")
            self.lbl_status.setStyleSheet("background-color: #fd7e14; color: white; border-radius: 6px; padding: 6px 12px; font-size: 11px; font-weight: bold;")
            self.worker.start() 
        else:
            self.is_paused_state = True
            self.worker.stop()
            self.btn_pause.setText("Resume")
            self.lbl_status.setText("PAUSED")
            self.lbl_status.setStyleSheet("background-color: #555; color: white; border-radius: 6px; padding: 6px 12px; font-size: 11px; font-weight: bold;")
            self.lbl_speed.setText("0 B/s")

    def auto_resume(self):
        if "ERROR" in self.lbl_status.text(): self.toggle_pause() 
    def open_folder(self):
        if not os.path.exists(self.save_path):
            try: os.makedirs(self.save_path)
            except: pass     
        if platform.system() == "Windows": os.startfile(self.save_path)
        elif platform.system() == "Darwin": subprocess.Popen(["open", self.save_path])

# --- 6. MAIN WINDOW ---

class DriveDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Portable Drive Downloader")
        self.resize(700, 800)
        self.workers = {}
        self.session_token = None 
        self.setStyleSheet(DARK_THEME)
        central = QWidget()
        self.setCentralWidget(central)
        self.layout = QVBoxLayout(central)
        self.layout.setSpacing(15)
        self.layout.setContentsMargins(20, 20, 20, 20)

        header_layout = QHBoxLayout()
        title_layout = QVBoxLayout()
        app_title = QLabel("Drive Downloader")
        app_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        app_subtitle = QLabel("Portable & Secure Rclone Client")
        app_subtitle.setStyleSheet("font-size: 13px; color: #bbbbbb;")
        title_layout.addWidget(app_title)
        title_layout.addWidget(app_subtitle)
        self.lbl_network = QLabel("Checking...")
        self.lbl_network.setFixedSize(120, 30)
        self.lbl_network.setAlignment(Qt.AlignCenter)
        self.lbl_network.setStyleSheet("background-color: #333; color: #aaa; border-radius: 15px; font-weight: bold; font-size: 12px;")
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_network)
        self.layout.addLayout(header_layout)

        auth_card = QFrame()
        auth_card.setObjectName("DashboardCard")
        auth_layout = QHBoxLayout(auth_card)
        auth_layout.setContentsMargins(15, 15, 15, 15)
        self.lbl_auth_status = QLabel("Not Logged In")
        self.lbl_auth_status.setStyleSheet("font-weight: bold; color: #ff6b6b; font-size: 14px;")
        self.btn_login = QPushButton("Login with Google")
        self.btn_login.setObjectName("PrimaryBtn")
        self.btn_login.setCursor(Qt.PointingHandCursor)
        self.btn_login.setMinimumHeight(32) 
        self.btn_login.clicked.connect(self.authenticate)
        self.btn_logout = QPushButton("Logout")
        self.btn_logout.setCursor(Qt.PointingHandCursor)
        self.btn_logout.setMinimumHeight(32) 
        self.btn_logout.clicked.connect(self.prompt_logout)
        self.btn_logout.hide()
        auth_layout.addWidget(self.lbl_auth_status)
        auth_layout.addStretch()
        auth_layout.addWidget(self.btn_login)
        auth_layout.addWidget(self.btn_logout)
        self.layout.addWidget(auth_card)

        self.install_progress = QProgressBar()
        self.install_progress.hide()
        self.layout.addWidget(self.install_progress)

        input_layout = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Paste Google Drive folder link here...")
        self.btn_dl = QPushButton("Download")
        self.btn_dl.setObjectName("PrimaryBtn")
        self.btn_dl.setCursor(Qt.PointingHandCursor)
        self.btn_dl.setFixedSize(120, 36) 
        self.btn_dl.clicked.connect(self.start_download)
        input_layout.addWidget(self.input)
        input_layout.addWidget(self.btn_dl)
        self.layout.addLayout(input_layout)

        lbl_tasks = QLabel("Active Downloads")
        lbl_tasks.setStyleSheet("font-weight: bold; color: #e0e0e0; margin-top: 10px;")
        self.layout.addWidget(lbl_tasks)
        self.list_widget = QListWidget()
        self.layout.addWidget(self.list_widget)

        self.check_rclone_exists()
        if os.path.exists(get_rclone_config_path()):
            try: os.remove(get_rclone_config_path())
            except: pass
        self.load_tasks_from_disk()
        self.update_ui_state() 

        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.save_tasks_to_disk)
        self.autosave_timer.start(5000)
        self.net_monitor = NetworkMonitor()
        self.net_monitor.connection_changed.connect(self.on_network_change)
        self.net_monitor.start()

    def authenticate(self):
        try:
            if platform.system() == "Windows":
                subprocess.run("taskkill /F /IM rclone.exe", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.run("pkill -f rclone", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            sleep(1)
            cmd = [self.rclone_path, "authorize", "drive"]
            startupinfo = None
            creation_flags = 0
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creation_flags = subprocess.CREATE_NO_WINDOW
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo, creationflags=creation_flags)
            stdout, stderr = process.communicate()
            match = re.search(r'(\{.*"access_token".*\})', stdout, re.DOTALL)
            if match:
                token_json = match.group(0)
                json.loads(token_json) 
                self.session_token = token_json
                self.lbl_auth_status.setText("Logged In")
                self.lbl_auth_status.setStyleSheet("font-weight: bold; color: #2ecc71; font-size: 14px;")
                self.btn_login.hide()
                self.btn_logout.show()
                self.update_ui_state()
                for worker in self.workers.values():
                    worker.token = self.session_token
            else:
                if "address already in use" in stderr: raise Exception("Port blocked. Restart app.")
                raise Exception("Login failed. Check internet.")
        except Exception as e: QMessageBox.critical(self, "Auth Error", str(e))

    def prompt_logout(self):
        reply = QMessageBox.question(self, "Logout", "End session? Downloads will stop.", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.session_token = None
            self.lbl_auth_status.setText("Not Logged In")
            self.lbl_auth_status.setStyleSheet("font-weight: bold; color: #ff6b6b; font-size: 14px;")
            self.btn_logout.hide()
            self.btn_login.show()
            self.update_ui_state()

    def update_ui_state(self):
        is_logged_in = self.session_token is not None
        self.input.setEnabled(is_logged_in)
        self.btn_dl.setEnabled(is_logged_in)
        if is_logged_in: self.input.setPlaceholderText("Paste Google Drive Folder Link here...")
        else: self.input.setPlaceholderText("Please Login to Start Downloading...")
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)
            if widget: widget.set_session_active(is_logged_in)

    def prompt_remove_task(self, item, worker):
        reply = QMessageBox.question(self, "Remove", "Remove task from list?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if worker.isRunning():
                worker.stop()
                worker.wait()
            if id(item) in self.workers: del self.workers[id(item)]
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
            self.save_tasks_to_disk()

    def on_network_change(self, is_online):
        if is_online:
            self.lbl_network.setText("Online")
            self.lbl_network.setStyleSheet("background-color: #198754; color: white; border-radius: 15px; font-weight: bold; font-size: 12px;")
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                widget = self.list_widget.itemWidget(item)
                if widget: widget.auto_resume()
        else:
            self.lbl_network.setText("Offline")
            self.lbl_network.setStyleSheet("background-color: #dc3545; color: white; border-radius: 15px; font-weight: bold; font-size: 12px;")

    def get_tasks_file_path(self):
        base = get_app_root()
        return os.path.join(base, "tasks.json")

    def save_tasks_to_disk(self):
        tasks_data = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)
            if widget: tasks_data.append(widget.get_state())
        final_path = self.get_tasks_file_path()
        temp_path = final_path + ".tmp"
        try:
            with open(temp_path, 'w') as f: json.dump(tasks_data, f, indent=4)
            if os.path.exists(final_path): os.remove(final_path)
            os.rename(temp_path, final_path)
        except: pass

    def load_tasks_from_disk(self):
        path = self.get_tasks_file_path()
        if not os.path.exists(path): return
        try:
            with open(path, 'r') as f: tasks = json.load(f)
            for t in tasks:
                self.add_task(t['id'], t['path'], auto_start=False, known_size=t.get('total_size', 0))
        except: pass

    def closeEvent(self, event):
        self.save_tasks_to_disk()
        if hasattr(self, 'autosave_timer'): self.autosave_timer.stop()
        if hasattr(self, 'net_monitor'):
            self.net_monitor.stop()
            if not self.net_monitor.wait(100): self.net_monitor.terminate()
        for worker in self.workers.values():
            if worker.isRunning():
                if worker.process: worker.process.kill()
                worker.terminate()
                worker.wait()
        event.accept()

    def check_rclone_exists(self):
        try:
            self.rclone_path = get_rclone_path()
            if not os.path.exists(self.rclone_path):
                self.start_rclone_install()
        except: pass

    def start_rclone_install(self):
        self.install_progress.show()
        self.installer = RcloneInstallerThread()
        self.installer.percent_signal.connect(self.install_progress.setValue)
        self.installer.finished_signal.connect(self.on_install_finished)
        self.installer.start()

    def on_install_finished(self, success, msg):
        self.install_progress.hide()
        if success: self.check_rclone_exists()
        else: QMessageBox.critical(self, "Error", msg)

    def start_download(self):
        if not self.session_token:
            QMessageBox.warning(self, "Login Required", "Please login first.")
            return
        raw_link = self.input.text()
        if not raw_link: return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        folder_id = DriveLinkParser.get_id(raw_link)
        QApplication.restoreOverrideCursor()
        if not folder_id:
            QMessageBox.warning(self, "Error", "Invalid Link")
            return
        save_dir = QFileDialog.getExistingDirectory(self, "Select Save Folder")
        if save_dir:
            self.add_task(folder_id, save_dir)
            self.input.clear()

    def add_task(self, fid, save_dir, auto_start=True, known_size=0):
        worker = DownloadWorker(self.rclone_path, fid, save_dir, token=self.session_token)
        item = QListWidgetItem(self.list_widget)
        item.setSizeHint(QSize(0, 260))
        dash = DownloadDashboard(fid, save_dir, worker, initial_size=known_size)
        self.list_widget.setItemWidget(item, dash)
        self.workers[id(item)] = worker
        dash.remove_requested.connect(lambda: self.prompt_remove_task(item, worker))
        if auto_start: worker.start()
        self.save_tasks_to_disk()
        self.update_ui_state()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DriveDownloader()
    window.show()
    sys.exit(app.exec())