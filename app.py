import sys
import os
import subprocess
import threading
import shlex
import shutil
import urllib.request
import urllib.parse
import html
import time
import re
import json
import keyring
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel,
                             QCheckBox, QSplitter, QComboBox, QListWidget, QListWidgetItem,
                             QDialog, QFormLayout, QDialogButtonBox, QMenu)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QPixmap, QTextCursor, QIcon
from PySide6.QtSvgWidgets import QSvgWidget


from migrate import PERSONAL_PROFILE_ROOT, AGENT_PROFILE_ROOT, MEMORIES_DIR

# Convert Path objects to strings for compatibility with os.path and subprocess
PERSONAL_PROFILE_ROOT = str(PERSONAL_PROFILE_ROOT)
AGENT_PROFILE_ROOT = str(AGENT_PROFILE_ROOT)
MEMORIES_DIR = str(MEMORIES_DIR)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
# If running as a frozen bundle, use the resources path
if getattr(sys, 'frozen', False):
    # PyInstaller bundle path is Contents/MacOS/app, so resources are in Contents/Resources/
    # or just adjacent depending on --add-data
    HARNESS_DIR = os.path.join(APP_DIR, "browser-harness")
else:
    HARNESS_DIR = os.path.join(os.path.dirname(APP_DIR), "browser-harness")

AGENT_WORKSPACE = os.path.join(HARNESS_DIR, "agent-workspace")
SHARED_PROMPT_PATH = os.path.join(AGENT_WORKSPACE, "browser_agent_prompt.md")
USER_CARD_PATH = os.path.join(AGENT_WORKSPACE, "user_card.md")
BROWSER_PORT = "9223"
BU_CDP_URL = f"http://127.0.0.1:{BROWSER_PORT}"
SCREENSHOT_PATH = "/tmp/unibrowse-live.png"

def get_version():
    try:
        v_path = os.path.join(APP_DIR, "assets", "version.txt")
        if os.path.exists(v_path):
            with open(v_path, "r") as f:
                return f.read().strip()
    except Exception:
        pass
    return "v0.0.1-dev"

VERSION = get_version()
DEFAULT_MODEL = os.environ.get("UNIBROWSE_MODEL", "google/antigravity-gemini-3-flash")
DEFAULT_VARIANT = os.environ.get("UNIBROWSE_VARIANT", "")
DEFAULT_PATH = ":".join(
    [
        os.path.expanduser("~/.local/bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
)


def resolve_command(name):
    return shutil.which(name, path=agent_env().get("PATH")) or name


def cdp_is_ready(url=BU_CDP_URL):
    try:
        with urllib.request.urlopen(f"{url}/json/version", timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def personal_chrome_is_running():
    try:
        result = subprocess.run(
            ["pgrep", "-x", "Google Chrome"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except Exception:
        return False


def agent_env():
    env = os.environ.copy()
    env["PATH"] = env.get("PATH", DEFAULT_PATH)
    for path_entry in reversed(DEFAULT_PATH.split(":")):
        if path_entry not in env["PATH"].split(":"):
            env["PATH"] = f"{path_entry}:{env['PATH']}"
    env["BU_CDP_URL"] = env.get("UNIBROWSE_CDP_URL", BU_CDP_URL)
    env["BH_NO_ACTIVATE"] = "1"
    env["BU_NAME"] = "unibrowse"
    env["BH_AGENT_WORKSPACE"] = AGENT_WORKSPACE
    env["CLAUDE_MEM_DATA_DIR"] = MEMORIES_DIR
    return env


def load_agent_prompt():
    try:
        with open(SHARED_PROMPT_PATH, "r", encoding="utf-8") as prompt_file:
            prompt = prompt_file.read().strip()
            if prompt:
                return prompt
    except FileNotFoundError:
        print(f"Warning: Shared prompt file not found at {SHARED_PROMPT_PATH}")
    except OSError as e:
        print(f"Error reading shared prompt file: {e}")

    # Grounded fail-safe fallback
    return (
        "You control the current browser through browser-harness. Treat browser work as stateful. "
        "Use helpers directly, verify every meaningful action, keep BH_NO_ACTIVATE=1 in stealth mode, "
        "and use memory only on demand when ambiguity or missing preferences require it."
    )


def is_internal_tab(tab):
    url = tab.get("url") or ""
    return (
        "omnibox-popup" in url
        or "aim.html" in url
        or url.startswith("chrome://")
        or url.startswith("chrome-error://chromewebdata/")
    )


def summarize_tab(tab):
    title = tab.get("title") or "(Untitled)"
    url = tab.get("url") or "about:blank"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        short_url = parsed.netloc + (parsed.path[:32] if parsed.path else "")
    else:
        short_url = parsed.path or parsed.netloc or url
    return f"{title} · {short_url}"


def run_harness(args_or_code, timeout=10, env=None, cwd=HARNESS_DIR):
    command = [resolve_command("browser-harness")]
    if isinstance(args_or_code, str):
        command.extend(["-c", args_or_code])
    else:
        command.extend(list(args_or_code))
    return subprocess.check_output(
        command,
        stderr=subprocess.STDOUT,
        text=True,
        env=env or agent_env(),
        cwd=cwd,
        timeout=timeout,
    )


def run_unibrowse_backend(prompt, model="", variant=""):
    command = [resolve_command("opencode"), "run"]
    model = (model or "").strip()
    variant = (variant or "").strip()
    if model:
        command.extend(["--model", model])
    if variant:
        command.extend(["--variant", variant])
    command.append(prompt)
    return command


def stream_process(command, env=None, cwd=HARNESS_DIR):
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env or agent_env(),
        cwd=cwd,
    )

def load_user_card():
    try:
        if os.path.exists(USER_CARD_PATH):
            with open(USER_CARD_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return "No User Card available."


class CredentialDialog(QDialog):
    def __init__(self, domain, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Login Required: {domain}")
        self.setMinimumWidth(360)
        
        layout = QVBoxLayout(self)
        label = QLabel(f"The agent needs credentials for <b>{domain}</b>")
        label.setWordWrap(True)
        layout.addWidget(label)

        form = QFormLayout()
        self.username_field = QLineEdit()
        self.password_field = QLineEdit()
        self.password_field.setEchoMode(QLineEdit.Password)
        
        form.addRow("Username/Email:", self.username_field)
        form.addRow("Password:", self.password_field)
        layout.addLayout(form)

        self.save_checkbox = QCheckBox("Save to macOS Keychain")
        self.save_checkbox.setChecked(True)
        layout.addWidget(self.save_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        return {
            "username": self.username_field.text().strip(),
            "password": self.password_field.text(),
            "save": self.save_checkbox.isChecked()
        }


class UnibrowseApp(QMainWindow):
    output_signal = Signal(str)
    progress_signal = Signal(str)
    status_signal = Signal(str)
    screenshot_signal = Signal(str)
    task_state_signal = Signal(str, str)
    tabs_signal = Signal(list, str) # tabs, active_id
    auth_request_signal = Signal(str) # domain
    browser_ready_signal = Signal()
    task_done_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"unibrowse {VERSION}")
        self.setWindowIcon(QIcon(os.path.join(APP_DIR, "assets", "logo.svg")))
        self.setMinimumSize(1280, 820)
        self.initialize_state()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        self.setup_activity_panel(main_layout)
        self.setup_input_controls(main_layout)
        self.setup_status_controls(main_layout)
        self.setup_browser_controls(main_layout)

        sidebar = self.setup_sidebar()

        splitter.addWidget(main_panel)
        splitter.addWidget(sidebar)
        splitter.setSizes([560, 720])

        self.connect_signals()
        self.init_agent()

    def initialize_state(self):
        self.current_tabs = []
        self.active_tab_id = None
        self.tabs_busy = False
        self.current_process = None
        self.stop_requested = False
        self.autotest_started = False
        self.task_running = False
        self.screenshot_busy = False
        self.task_start_time = None
        self.task_finalized = False
        self.last_kind = None
        self.last_card_id = None
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self.update_elapsed_time)

    def setup_activity_panel(self, layout):
        header_layout = QHBoxLayout()
        
        self.logo_widget = QSvgWidget(os.path.join(APP_DIR, "assets", "logo.svg"))
        self.logo_widget.setFixedSize(32, 32)
        header_layout.addWidget(self.logo_widget)

        feed_title = QLabel("unibrowse Activity")
        feed_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        header_layout.addWidget(feed_title)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)

        self.activity = QTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setStyleSheet("""
            QTextEdit {
                background-color: #0b0d12;
                color: #e8eaf0;
                border: 1px solid #1c2128;
                border-radius: 12px;
                padding: 12px;
                font-family: 'Roboto', 'Helvetica Neue', Arial, sans-serif;
                font-size: 14px;
            }
        """)
        layout.addWidget(self.activity, 1)

    def setup_input_controls(self, layout):
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a command for the browser agent...")
        self.input_field.returnPressed.connect(self.send_command)
        input_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_command)
        input_layout.addWidget(self.send_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_task)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b141a;
                color: #ff9aa2;
            }
            QPushButton:enabled {
                background-color: #7a1b24;
                color: white;
            }
        """)
        input_layout.addWidget(self.stop_btn)
        layout.addLayout(input_layout)

    def setup_status_controls(self, layout):
        state_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #5b6472; font-weight: 600;")
        state_layout.addWidget(self.status_label, 1)

        self.task_badge = QLabel("IDLE")
        self.task_badge.setAlignment(Qt.AlignCenter)
        self.task_badge.setMinimumWidth(92)
        self.task_badge.setStyleSheet("background:#e9edf5; color:#445064; border-radius:10px; padding:5px 10px; font-weight:800;")
        state_layout.addWidget(self.task_badge)

        self.elapsed_label = QLabel("00:00")
        self.elapsed_label.setStyleSheet("color:#5b6472; font-weight:700; min-width:52px;")
        state_layout.addWidget(self.elapsed_label)
        layout.addLayout(state_layout)

    def setup_browser_controls(self, layout):
        browser_layout = QHBoxLayout()
        browser_layout.addWidget(QLabel("Browser"))
        self.browser_mode = QComboBox()
        self.browser_mode.addItems(["Agent profile", "Personal Chrome", "Remote CDP"])
        self.browser_mode.currentTextChanged.connect(self.update_browser_mode)
        browser_layout.addWidget(self.browser_mode)

        self.sync_profile_btn = QPushButton("Sync Profiles")
        self.sync_profile_btn.clicked.connect(self.sync_profiles_on_demand)
        browser_layout.addWidget(self.sync_profile_btn)

        self.refresh_tabs_btn = QPushButton("Refresh Tabs")
        self.refresh_tabs_btn.clicked.connect(self.sync_tabs)
        browser_layout.addWidget(self.refresh_tabs_btn)

        self.cleanup_tabs_btn = QPushButton("Cleanup Tabs")
        self.cleanup_tabs_btn.clicked.connect(self.cleanup_tabs_on_demand)
        browser_layout.addWidget(self.cleanup_tabs_btn)

        self.upload_remote_btn = QPushButton("Mirror Workspace")
        self.upload_remote_btn.clicked.connect(self.upload_to_server_on_demand)
        self.upload_remote_btn.setToolTip("Mirrors your profiles and memories to the remote server")
        browser_layout.addWidget(self.upload_remote_btn)
        
        layout.addLayout(browser_layout)

        remote_layout = QHBoxLayout()
        self.remote_toggle = QCheckBox("Remote backend")
        self.remote_toggle.stateChanged.connect(self.update_backend_mode)
        remote_layout.addWidget(self.remote_toggle)

        self.remote_field = QLineEdit()
        self.remote_field.setPlaceholderText("Remote Server IP (e.g. 192.168.1.50)")
        self.remote_field.setEnabled(False)
        remote_layout.addWidget(self.remote_field)
        layout.addLayout(remote_layout)

        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Model"))
        self.model_field = QLineEdit()
        self.model_field.setPlaceholderText("provider/model")
        self.model_field.setText(DEFAULT_MODEL)
        model_layout.addWidget(self.model_field)

        model_layout.addWidget(QLabel("Variant"))
        self.variant_field = QLineEdit()
        self.variant_field.setPlaceholderText("optional")
        self.variant_field.setText(DEFAULT_VARIANT)
        model_layout.addWidget(self.variant_field)
        layout.addLayout(model_layout)

        debug_layout = QHBoxLayout()
        self.debug_toggle = QCheckBox("Show Debug Messages")
        self.debug_toggle.setChecked(False)
        debug_layout.addWidget(self.debug_toggle)
        debug_layout.addStretch()
        layout.addLayout(debug_layout)

    def setup_sidebar(self):
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)

        tab_title = QLabel("Browser Tabs")
        tab_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        sidebar_layout.addWidget(tab_title)

        self.tab_list = QListWidget()
        self.tab_list.setMinimumHeight(140)
        self.tab_list.setMaximumHeight(200)
        self.tab_list.setStyleSheet("""
            QListWidget {
                background-color: #0d1117;
                border: 1px solid #30363d;
                border-radius: 8px;
                color: #c9d1d9;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #21262d;
            }
            QListWidget::item:selected {
                background-color: #1f6feb;
                color: white;
            }
        """)
        self.tab_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_list.customContextMenuRequested.connect(self.show_tab_context_menu)
        self.tab_list.itemClicked.connect(self.switch_to_selected_tab)
        sidebar_layout.addWidget(self.tab_list)

        screenshot_title = QLabel("Live Screenshot")
        screenshot_title.setStyleSheet("font-size: 18px; font-weight: 700; margin-top: 10px;")
        sidebar_layout.addWidget(screenshot_title)

        self.screenshot_label = QLabel("No screenshot yet")
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_label.setMinimumSize(560, 520)
        self.screenshot_label.setStyleSheet("background-color: #07090d; color: #8b93a3; border: 1px solid #262b36; border-radius: 12px;")
        sidebar_layout.addWidget(self.screenshot_label, 1)
        return sidebar

    def connect_signals(self):
        self.output_signal.connect(self._on_output_signal)
        self.progress_signal.connect(self._on_progress_signal)
        self.status_signal.connect(self.status_label.setText)
        self.screenshot_signal.connect(self.update_screenshot)
        self.task_state_signal.connect(self.set_task_state)
        self.tabs_signal.connect(self.update_tab_list_ui)
        self.auth_request_signal.connect(self.handle_auth_request)
        self.browser_ready_signal.connect(self.start_autotest_if_requested)
        self.task_done_signal.connect(self.quit_after_autotest)

    def handle_auth_request(self, domain):
        dialog = CredentialDialog(domain, self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if data["save"] and data["username"] and data["password"]:
                try:
                    # Save to Keychain
                    # Service: unibrowse:<domain>
                    service = f"unibrowse:{domain}"
                    keyring.set_password(service, data["username"], data["password"])
                    # Save metadata: domain -> last used username
                    keyring.set_password("unibrowse:Metadata", domain, data["username"])
                    self.append_activity(f"Credentials for {domain} saved to Keychain.", "progress")
                except Exception as e:
                    self.append_activity(f"Failed to save to Keychain: {e}", "error")
            
            self.append_activity(f"Auth provided for {domain}. Please resubmit the task to continue.", "progress")
        else:
            self.append_activity(f"Auth request for {domain} cancelled.", "progress")

    def _on_output_signal(self, text):
        clean = self.clean_text(text).strip()
        if "AGENT_SIGNAL:AUTH_REQUEST:" in clean:
            try:
                # Extract JSON payload
                json_str = clean.split("AGENT_SIGNAL:AUTH_REQUEST:", 1)[1].strip()
                payload = json.loads(json_str)
                domain = payload.get("domain", "unknown site")
                self.auth_request_signal.emit(domain)
                return 
            except Exception:
                pass
        
        if "AGENT_SIGNAL:LEARNING_FALLBACK:" in clean:
            try:
                json_str = clean.split("AGENT_SIGNAL:LEARNING_FALLBACK:", 1)[1].strip()
                payload = json.loads(json_str)
                cat = payload.get("category", "info")
                content = payload.get("content", "")
                self.append_activity(f"Agent learned something ({cat}):\n{content}", "context")
                return
            except Exception:
                pass

        if clean.startswith("$"):
            self.append_activity(text, "command")
        elif clean.startswith(">"):
            self.append_activity(text, "you")
        else:
            self.append_activity(text, "agent")

    def _on_progress_signal(self, text):
        self.append_activity(text, "progress")


    def update_backend_mode(self):
        if self.remote_toggle.isChecked() and self.browser_mode.currentText() != "Remote CDP":
            self.browser_mode.setCurrentText("Remote CDP")
            return
        self.update_browser_mode()

    def update_browser_mode(self):
        remote = self.browser_mode.currentText() == "Remote CDP" or self.remote_toggle.isChecked()
        if self.remote_toggle.isChecked() != remote:
            self.remote_toggle.blockSignals(True)
            self.remote_toggle.setChecked(remote)
            self.remote_toggle.blockSignals(False)
        self.remote_field.setEnabled(remote)
        if remote:
            self.status_signal.emit("Remote mode (enter CDP URL)")
            self.progress_signal.emit("Mode: remote backend. Local Chrome launch disabled.")
        elif self.browser_mode.currentText() == "Personal Chrome":
            self.status_signal.emit("Personal Chrome mode")
            self.progress_signal.emit("Mode: personal Chrome profile. Best used when normal Chrome is closed first.")
        else:
            self.status_signal.emit("Local mode")
            self.progress_signal.emit("Mode: local backend. Dedicated Chrome profile will be used.")

    def init_agent(self):
        self.append_activity(f"Initializing unibrowse {VERSION}...", "agent")
        self.append_activity("Thinking: prepare a stealth browser session without focusing Chrome.", "progress")
        self.append_activity("Task: prepare agent profile. Full profile sync is on demand.", "progress")
        self.append_activity(f"Model preference: {self.model_field.text().strip() or 'unibrowse default'}", "progress")
        threading.Thread(target=self.run_migration).start()

    def run_migration(self):
        try:
            from migrate import ensure_agent_profile
            profile_path = ensure_agent_profile()
            self.output_signal.emit(f"Profile ready at: {profile_path}")
            self.progress_signal.emit("Task complete: profile is ready.")
            self.start_browser(profile_path)
        except Exception as e:
            self.output_signal.emit(f"Initialization Error: {e}")
            self.progress_signal.emit(f"Error: initialization failed: {e}")

    def start_browser(self, profile_path):
        if self.browser_mode.currentText() == "Remote CDP" or self.remote_toggle.isChecked():
            self.output_signal.emit("Remote mode enabled. Skipping local Chrome launch.")
            self.status_signal.emit("Remote backend")
            self.capture_live_screenshot()
            self.browser_ready_signal.emit()
            self.sync_tabs()
            return
        personal_mode = self.browser_mode.currentText() == "Personal Chrome"
        browser_label = "Personal Chrome" if personal_mode else "Stealth Browser"
        launch_profile = PERSONAL_PROFILE_ROOT if personal_mode else profile_path
        self.output_signal.emit(f"Launching {browser_label}...")
        self.progress_signal.emit(f"Task: launch {browser_label.lower()} backend on port 9223.")
        if cdp_is_ready():
            self.output_signal.emit("Existing browser backend found on port 9223. Reusing it.")
            self.progress_signal.emit("Task complete: reused existing browser backend.")
            self.status_signal.emit(f"Online ({browser_label})")
            self.capture_live_screenshot()
            self.browser_ready_signal.emit()
            self.sync_tabs()
            return

        if personal_mode and personal_chrome_is_running():
            message = (
                "Personal Chrome is already running, but no controllable browser backend "
                "was found on port 9223. Close Chrome completely, then relaunch this app "
                "or switch to Agent profile mode."
            )
            self.output_signal.emit(message)
            self.progress_signal.emit("Blocked: personal Chrome is already open without remote debugging.")
            self.status_signal.emit("Personal Chrome already open")
            return

        chrome_args = [
            f"--remote-debugging-port={BROWSER_PORT}",
            f"--user-data-dir={launch_profile}",
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1200,1000",
            "about:blank",
        ]
        chrome_cmd = ["open", "-n", "-a", "Google Chrome", "--args", *chrome_args]
        # Set environment variables for the agent processes
        os.environ.update(agent_env())
        
        subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=agent_env())
        for _ in range(30):
            if cdp_is_ready():
                break
            threading.Event().wait(0.2)
        self.output_signal.emit(f"{browser_label} connected on port 9223.")
        self.progress_signal.emit(f"Task complete: {browser_label.lower()} backend is running.")
        self.status_signal.emit(f"Online ({browser_label})")
        self.capture_live_screenshot()
        self.browser_ready_signal.emit()
        self.sync_tabs()

    def cleanup_tabs_on_demand(self):
        self.cleanup_tabs_btn.setEnabled(False)
        self.append_activity("Cleaning up cluttered/duplicate tabs...", "progress")

        def worker():
            try:
                # Add agent-workspace to path to reach agent_helpers
                import sys
                sys.path.insert(0, AGENT_WORKSPACE)
                from agent_helpers import cleanup_tabs
                
                # We need to run inside harness env
                res = run_harness("from agent_helpers import cleanup_tabs; print(cleanup_tabs())", env=self.current_env())
                self.progress_signal.emit(f"Cleanup: {res.strip()}")
                self.sync_tabs()
            except Exception as e:
                self.progress_signal.emit(f"Cleanup failed: {e}")
            finally:
                self.cleanup_tabs_btn.setEnabled(True)

        threading.Thread(target=worker).start()

    def upload_to_server_on_demand(self):
        server_ip = self.remote_field.text().strip()
        if not server_ip:
            self.append_activity("Please enter a Remote Server IP first.", "error")
            return
        
        self.upload_remote_btn.setEnabled(False)
        self.append_activity(f"Mirroring workspace to {server_ip}...", "progress")

        def worker():
            try:
                from migrate import sync_to_remote
                success = sync_to_remote(server_ip)
                if success:
                    self.progress_signal.emit(f"Workspace mirrored to {server_ip}.")
                else:
                    self.progress_signal.emit(f"Mirroring failed for {server_ip}.")
            except Exception as e:
                self.progress_signal.emit(f"Mirroring error: {e}")
            finally:
                self.upload_remote_btn.setEnabled(True)

        threading.Thread(target=worker).start()

    def sync_profiles_on_demand(self):
        self.sync_profile_btn.setEnabled(False)
        self.append_activity("Syncing personal Chrome profile and agent profile...", "progress")

        def worker():
            try:
                from migrate import sync_profiles
                profile_path = sync_profiles()
                self.progress_signal.emit(f"Profile sync complete: {profile_path}")
            except Exception as e:
                self.progress_signal.emit(f"Profile sync failed: {e}")
            finally:
                self.sync_profile_btn.setEnabled(True)

        threading.Thread(target=worker).start()

    def start_autotest_if_requested(self):
        if os.environ.get("UNIBROWSE_AUTOTEST") != "1" or self.autotest_started:
            return
        self.autotest_started = True
        self.append_activity("Autotest: running url command and live screenshot check.", "progress")

        def run():
            self.input_field.setText("url: https://example.com")
            self.send_command()

        QTimer.singleShot(2000, run)

    def quit_after_autotest(self):
        if os.environ.get("UNIBROWSE_AUTOTEST") != "1":
            return
        self.append_activity("Autotest: complete. Closing app after final screenshot refresh.", "progress")
        QTimer.singleShot(6000, QApplication.instance().quit)

    def send_command(self):
        cmd = self.input_field.text().strip()
        if not cmd:
            return
        if self.task_running:
            self.append_activity("Busy: wait for the current agent task to finish.", "progress")
            return
        
        self.append_activity(f"\n> {cmd}", "you")
        self.append_activity(f"Goal: {cmd}", "progress")
        self.append_activity("Thinking: choose the least disruptive browser-harness path.", "progress")
        self.input_field.clear()
        
        # Run the command through browser-harness CLI
        threading.Thread(target=self.execute_agent_task, args=(cmd,)).start()

    def current_env(self):
        env = agent_env()
        is_remote = self.browser_mode.currentText() == "Remote CDP" or self.remote_toggle.isChecked()
        
        if is_remote:
            server_ip = self.remote_field.text().strip()
            if server_ip:
                # If just an IP is provided, assume standard port
                if ":" not in server_ip:
                    url = f"http://{server_ip}:9223"
                else:
                    url = server_ip if server_ip.startswith("http") else f"http://{server_ip}"
                
                env["BU_CDP_URL"] = url
                env["OPENCODE_AGENT_CDP_URL"] = url
        return env

    def build_runtime_context(self):
        lines = [
            "Runtime Context:",
            f"- Browser mode: {self.browser_mode.currentText()}",
            "- Stealth/background: BH_NO_ACTIVATE=1",
            f"- CDP URL: {self.current_env().get('BU_CDP_URL', BU_CDP_URL)}",
        ]
        visible_tabs = []
        for index, tab in enumerate(self.current_tabs):
            if is_internal_tab(tab):
                continue
            target_id = tab.get("targetId") or "unknown"
            active_marker = " active" if target_id == self.active_tab_id else ""
            visible_tabs.append(f"  - [{index}] {summarize_tab(tab)}{active_marker} | id={target_id}")
        if visible_tabs:
            lines.append("- Current tabs:")
            lines.extend(visible_tabs[:12])
        else:
            lines.append("- Current tabs: not loaded; use page_info/list_tabs if tab state matters")
        lines.append(f"- Live screenshot path: {SCREENSHOT_PATH}")
        return "\n".join(lines)

    def fetch_dynamic_context(self, task, domain):
        context_parts = []
        
        # 1. Domain Trigger: Search for site-specific heals
        if domain and domain != "about:blank":
            try:
                # Direct search for site fixes
                port = 37700 + (os.getuid() % 100)
                # Quick check if port is open to avoid 3s timeout
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1)
                    if s.connect_ex(('127.0.0.1', port)) == 0:
                        url = f"http://127.0.0.1:{port}/api/search/observations?query={urllib.parse.quote('site fix for ' + domain)}&limit=5"
                        with urllib.request.urlopen(url, timeout=2) as response:
                            payload = json.loads(response.read().decode("utf-8"))
                            items = payload.get("items") or []
                            if items:
                                lines = []
                                for item in items:
                                    title = self.clean_text(str(item.get("title") or item.get("subtitle") or "")).strip()
                                    if title and "plugin loading" not in title.lower():
                                        lines.append(f"- {title}")
                                if lines:
                                    context_parts.append(f"Site Adaptations for {domain}:\n" + "\n".join(lines))
            except Exception:
                pass

        # 2. Personal Trigger: Check for pronouns or identity markers
        personal_markers = ["my", "me", "i", "account", "login", "password"]
        if any(m in task.lower().split() for m in personal_markers):
            # We already have the User Card, but we could pull more specific facts
            pass
            
        return "\n\n".join(context_parts)

    def build_task_prompt(self, task):
        # Layer 0: Global Instructions
        base_prompt = load_agent_prompt()
        
        # Layer 1: Persistent Personal Info
        user_card = load_user_card()
        
        # Extract domain for dynamic context
        current_domain = "unknown"
        try:
            # We can get domain from active_tab or current_tabs
            for tab in self.current_tabs:
                if tab.get("targetId") == self.active_tab_id:
                    url = tab.get("url", "")
                    current_domain = urllib.parse.urlparse(url).netloc
                    break
        except Exception:
            pass
            
        # Layer 2: Dynamic Site/Task Context
        dynamic_context = self.fetch_dynamic_context(task, current_domain)
        
        # Layer 3: Runtime State
        runtime_state = self.build_runtime_context()
        
        full_prompt = (
            f"{base_prompt}\n\n"
            f"## User Profile (Persistent Context)\n{user_card}\n\n"
        )
        
        if dynamic_context:
            full_prompt += f"## Site-Specific Heals (Dynamic Context)\n{dynamic_context}\n\n"
            
        full_prompt += (
            f"## Runtime State\n{runtime_state}\n\n"
            f"## User Task\n{task}"
        )
        
        return full_prompt

    def sync_tabs(self):
        if self.tabs_busy or self.task_running:
            return
        self.tabs_busy = True

        def worker():
            try:
                # Get tab list and current page info to find active tab
                script = "import json; print(json.dumps({'tabs': list_tabs(), 'current': page_info()}))"
                res = run_harness(script, env=self.current_env(), timeout=10)
                data = json.loads(res.strip())
                tabs = data.get('tabs', [])
                current_url = data.get('current', {}).get('url', '')
                
                # Try to find which tab matches the current page info
                active_id = ""
                for t in tabs:
                    if t.get('url') == current_url:
                        active_id = t.get('targetId')
                        break

                self.tabs_signal.emit(tabs, active_id)
            except Exception as e:
                # Log to stdout but don't disrupt UI flow
                print(f"Tab sync background error: {e}")
            finally:
                self.tabs_busy = False

        threading.Thread(target=worker).start()

    def update_tab_list_ui(self, tabs, active_id):
        self.current_tabs = tabs
        self.active_tab_id = active_id
        self.tab_list.clear()
        for tab in tabs:
            tid = tab.get("targetId")
            
            if is_internal_tab(tab):
                continue
            
            display_title = summarize_tab(tab)
            if tid == active_id:
                display_title = f"● {display_title}"
            
            item = QListWidgetItem(display_title)
            item.setData(Qt.UserRole, tid)
            item.setToolTip(tab.get("url") or "about:blank")
            
            if tid == active_id:
                item.setSelected(True)
            
            self.tab_list.addItem(item)
        
    def switch_to_selected_tab(self, item):
        target_id = item.data(Qt.UserRole)
        if not target_id:
            return
        
        self.append_activity(f"Switching to tab: {target_id}", "progress")
        
        def worker():
            try:
                run_harness(f"switch_tab({target_id!r})", env=self.current_env(), timeout=10)
                self.capture_live_screenshot()
                self.sync_tabs()
            except Exception as e:
                self.append_activity(f"Failed to switch tab: {e}", "error")

        threading.Thread(target=worker).start()

    def show_tab_context_menu(self, position):
        item = self.tab_list.itemAt(position)
        if not item:
            return
            
        menu = QMenu()
        close_action = menu.addAction("Close Tab")
        
        action = menu.exec(self.tab_list.mapToGlobal(position))
        if action == close_action:
            target_id = item.data(Qt.UserRole)
            self.close_tab_by_id(target_id)

    def close_tab_by_id(self, target_id):
        self.append_activity(f"Closing tab: {target_id}", "progress")
        
        def worker():
            try:
                run_harness(f"cdp('Target.closeTarget', targetId={target_id!r})", env=self.current_env())
                self.sync_tabs()
            except Exception as e:
                self.append_activity(f"Failed to close tab: {e}", "error")

        threading.Thread(target=worker).start()

    def execute_agent_task(self, task):
        self.output_signal.emit("Agent thinking...")
        self.task_running = True
        self.stop_requested = False
        self.task_finalized = False
        self.task_state_signal.emit("running", "RUNNING")
        self.start_live_observation()
        
        fallback_cmd = None
        if task.startswith("bh:"):
            self.progress_signal.emit("Plan: run raw browser-harness Python snippet.")
            harness_cmd = [resolve_command("browser-harness"), "-c", task[3:].strip()]
        elif task.startswith("url:"):
            url = task[4:].strip()
            self.progress_signal.emit(f"Plan: open URL in stealth browser: {url}")
            harness_cmd = [resolve_command("browser-harness"), "-c", f"new_tab({url!r}); wait_for_load(); print(page_info())"]
        else:
            self.progress_signal.emit("Plan: delegate natural-language task to unibrowse with stealth browser env.")
            prompt = self.build_task_prompt(task)
            model = self.model_field.text().strip()
            variant = self.variant_field.text().strip()
            harness_cmd = run_unibrowse_backend(prompt, model, variant)
            fallback_cmd = [resolve_command("opencode"), "run", prompt] if model else None
        try:
            self.output_signal.emit("$ " + " ".join(shlex.quote(x) for x in harness_cmd))
            self.progress_signal.emit("Action: executing command.")
            result = self.run_streaming_command(harness_cmd)
            if result.returncode != 0:
                if self.stop_requested:
                    self.finish_task("error", "STOPPED", "Task stopped by user.")
                    return
                raise subprocess.CalledProcessError(result.returncode, harness_cmd, result.output)
            self.finish_task("done", "DONE", "Task complete: command finished.")
        except subprocess.CalledProcessError as e:
            if task and not task.startswith(("bh:", "url:")) and "ProviderModelNotFoundError" in e.output and fallback_cmd:
                self.output_signal.emit("Selected model was not found. Retrying with unibrowse default model...")
                self.progress_signal.emit("Recovery: selected model unavailable; retrying with unibrowse default.")
                try:
                    self.output_signal.emit("$ " + " ".join(shlex.quote(x) for x in fallback_cmd))
                    result = self.run_streaming_command(fallback_cmd)
                    if result.returncode != 0:
                        if self.stop_requested:
                            self.finish_task("error", "STOPPED", "Task stopped by user.")
                            return
                        raise subprocess.CalledProcessError(result.returncode, fallback_cmd, result.output)
                    self.finish_task("done", "DONE", "Task complete: command finished with fallback model.")
                    return
                except subprocess.CalledProcessError as fallback_error:
                    self.output_signal.emit(f"Fallback task failed:\n{fallback_error.output}")
                    self.finish_task("error", "ERROR", "Error: fallback command failed. Capturing browser state.")
                    return
            self.output_signal.emit(f"Task failed:\n{e.output}")
            self.finish_task("error", "ERROR", "Error: command failed. Capturing browser state.")
        except Exception as e:
            self.output_signal.emit(f"Task Error: {e}")
            self.finish_task("error", "ERROR", f"Error: {e}")
        finally:
            if not self.task_finalized:
                self.task_running = False
            self.stop_requested = False

    def run_streaming_command(self, command):
        output = []
        process = stream_process(command, env=self.current_env())
        self.current_process = process
        try:
            for line in process.stdout:
                output.append(line)
                self.output_signal.emit(line.rstrip())
            returncode = process.wait(timeout=600)
        except Exception:
            if process:
                process.kill()
                process.wait()
            raise
        finally:
            self.current_process = None
        return subprocess.CompletedProcess(command, returncode, "".join(output), None)

    def finish_task(self, state, label, message):
        if self.task_finalized:
            return
        self.task_finalized = True
        self.task_running = False
        self.task_state_signal.emit(state, label)
        self.progress_signal.emit(message)
        self.capture_live_screenshot()
        self.sync_tabs()
        self.task_done_signal.emit()
        
        # Trigger Reflection in background if task was successful
        if state == "done":
            threading.Thread(target=self.reflect_on_task).start()

    def reflect_on_task(self):
        try:
            # Reflection prompt to solidify learnings
            prompt = (
                "You are the Reflection Module. Reflect on the task just completed by the agent. "
                "1. If a site-specific roadblock was hit (like LockDown browser or a moved button), "
                "call store_learning('site_fix', content).\n"
                "2. If you learned a durable fact about the user, call store_learning('user_fact', content).\n"
                "3. If the User Card (agent-workspace/user_card.md) needs an update, use 'edit' to update it.\n"
                "4. If the browser is cluttered (too many tabs, duplicates), call 'cleanup_tabs()'.\n"
                "Be silent if there is nothing new to learn. Do not talk to the user."
            )
            # Use a slightly larger timeout for reflection
            harness_cmd = run_unibrowse_backend(prompt, DEFAULT_MODEL, "")
            subprocess.run(
                harness_cmd,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                env=self.current_env(),
                cwd=HARNESS_DIR,
                timeout=90
            )
            # Sync tabs one last time after reflection in case it changed something
            self.sync_tabs()
        except Exception as e:
            print(f"Reflection background error: {e}")

    def set_task_state(self, state, label):
        styles = {
            "idle": "background:#e9edf5; color:#445064; border-radius:10px; padding:5px 10px; font-weight:800;",
            "running": "background:#1d4ed8; color:white; border-radius:10px; padding:5px 10px; font-weight:800;",
            "done": "background:#15803d; color:white; border-radius:10px; padding:5px 10px; font-weight:800;",
            "error": "background:#b91c1c; color:white; border-radius:10px; padding:5px 10px; font-weight:800;",
        }
        self.task_badge.setText(label)
        self.task_badge.setStyleSheet(styles.get(state, styles["idle"]))
        if state == "running":
            self.task_start_time = time.time()
            self.elapsed_label.setText("00:00")
            self.elapsed_timer.start(1000)
            self.send_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.input_field.setEnabled(False)
            self.append_activity("Task started", "state")
        else:
            self.elapsed_timer.stop()
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.input_field.setEnabled(True)
            if state == "done":
                self.append_activity(f"Task finished in {self.elapsed_label.text()}", "done")
            elif state == "error":
                self.append_activity(f"Task stopped or failed after {self.elapsed_label.text()}", "error")

    def stop_task(self):
        if self.current_process:
            self.append_activity("Stopping agent task...", "progress")
            self.stop_requested = True
            self.stop_btn.setEnabled(False)
            try:
                self.current_process.terminate()
            except Exception:
                pass

    def update_elapsed_time(self):
        if not self.task_start_time:
            self.elapsed_label.setText("00:00")
            return
        elapsed = max(0, int(time.time() - self.task_start_time))
        minutes, seconds = divmod(elapsed, 60)
        self.elapsed_label.setText(f"{minutes:02d}:{seconds:02d}")

    def start_live_observation(self):
        def observer():
            while self.task_running:
                self.capture_live_screenshot()
                threading.Event().wait(3)

        threading.Thread(target=observer).start()

    def capture_live_screenshot(self):
        if self.screenshot_busy:
            return
        self.screenshot_busy = True

        def worker():
            try:
                run_harness(
                    f"ensure_real_tab(); capture_screenshot({SCREENSHOT_PATH!r})",
                    env=self.current_env(),
                    timeout=30,
                )
                self.screenshot_signal.emit(SCREENSHOT_PATH)
            except Exception as e:
                self.progress_signal.emit(f"Observation failed: screenshot unavailable ({e}).")
            finally:
                self.screenshot_busy = False

        threading.Thread(target=worker).start()

    def clean_text(self, text):
        # Remove ANSI escape sequences (more robust regex)
        ansi_escape = re.compile(r'(?:\x1B[@-Z\\-_]|[\x80-\x9F]|\x1B\[[0-?]*[ -/]*[@-~])')
        text = ansi_escape.sub('', text)
        # Remove other control characters except newline and tab
        text = "".join(ch for f in text.splitlines(True) for ch in f if ch == '\n' or ch == '\t' or ord(ch) >= 32)
        return text

    def format_markdown(self, text):
        # If debug is OFF, try to simplify tracebacks
        if not self.debug_toggle.isChecked() and ("Traceback (most recent call last):" in text or "SyntaxError" in text):
            lines = text.strip().splitlines()
            if lines:
                # The last line usually contains the actual error (e.g. SyntaxError: ...)
                last_line = lines[-1]
                return f'<div style="font-family: monospace; color: #ff9aa2; background: #211115; padding: 10px; border-radius: 6px; border-left: 4px solid #7a1b24;"><b>Execution Error:</b> {last_line}</div>'

        # If debug is ON or not a traceback, do regular formatting
        if "Traceback (most recent call last):" in text or "urllib.error.HTTPError" in text:
            # Wrap errors in a distinctive style
            return f'<div style="font-family: monospace; color: #ff9aa2; background: #211115; padding: 10px; border-radius: 6px; border-left: 4px solid #7a1b24;">{text}</div>'

        # Simple manual markdown for the terminal-style feed
        # Bold: **text**
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        # Headers: ### Header
        text = re.sub(r'^### (.*)', r'<h3 style="margin:12px 0 6px 0; color:#ffffff; font-weight:800;">\1</h3>', text, flags=re.MULTILINE)
        # Lists: 1. Item
        text = re.sub(r'^(\d+\.)\s+(.*)', r'<div style="margin-left:10px; margin-bottom:8px;"><b>\1</b> \2</div>', text, flags=re.MULTILINE)
        # Bullet Lists: - Item or * Item
        text = re.sub(r'^[*-]\s+(.*)', r'<div style="margin-left:20px; margin-bottom:6px;">• \1</div>', text, flags=re.MULTILINE)
        # Double newlines for paragraph spacing
        text = text.replace("\n\n", "<br><br>")
        # Fix weird character spacing/leaks
        text = text.replace("~~~~^^", " ")
        text = text.replace("~~~~~", " ")
        return text

    def append_activity(self, text, kind):
        stripped = self.clean_text(text).strip()
        if not stripped:
            return

        # Hide non-conversational noise unless debug is on
        if not self.debug_toggle.isChecked():
            # Hide system prompts, agent signals, background observation logs, and raw tracebacks
            if ("# Browser Agent Prompt" in stripped 
                or "AGENT_SIGNAL:" in stripped 
                or "Observation:" in stripped
                or "Traceback (most recent call last):" in stripped
                or 'File "' in stripped and ", line " in stripped):
                return
            # Hide startup/background progress unless it's an error
            if kind == "progress" and "error" not in stripped.lower() and "failed" not in stripped.lower():
                return
            # Hide initialization/thinking messages
            if kind == "agent" and (stripped.startswith("Initializing") or stripped.startswith("Thinking") or stripped.startswith("Launching") or "backend found" in stripped):
                return
            # Hide raw tool calls
            if stripped.startswith("[tool_call:"):
                return

        # Handle kind mapping
        color = "#e8eaf0"
        badge_bg = "#252b36"
        card_bg = "#151923"
        badge = "agent"

        if kind == "progress":
            color = "#8fd4ff"
            badge_bg = "#123044"
            card_bg = "#0f1d28"
            badge = "progress"
        elif kind == "context":
            color = "#d8b4fe"
            badge_bg = "#3b0764"
            card_bg = "#1e1333"
            badge = "context"
        elif kind == "state":
            color = "#dbeafe"
            badge_bg = "#1d4ed8"
            card_bg = "#111f3a"
            badge = "state"
        elif kind == "done":
            color = "#bbf7d0"
            badge_bg = "#15803d"
            card_bg = "#102317"
            badge = "done"
        elif stripped.startswith("$ "):
            color = "#ffd580"
            badge_bg = "#3b2d13"
            card_bg = "#1a1610"
            badge = "command"
        elif stripped.startswith(">"):
            color = "#b5f5c8"
            badge_bg = "#15371f"
            card_bg = "#101c14"
            badge = "you"
        elif stripped.startswith("[tool_call:") or "⚙" in stripped or "✱" in stripped:
            color = "#a5f3fc"
            badge_bg = "#083344"
            card_bg = "#081b25"
            badge = "tool"
        elif "failed" in stripped.lower() or "error" in stripped.lower():
            color = "#ff9aa2"
            badge_bg = "#441a20"
            card_bg = "#211115"
            badge = "error"

        # Apply formatting
        formatted_text = html.escape(stripped).replace("\n", "<br>")
        if kind == "agent":
            formatted_text = self.format_markdown(formatted_text)

        # If it's the same kind as before, try to append to the existing card
        if self.last_kind == kind and self.last_card_id and kind not in ["command", "tool"]:
            self.activity.moveCursor(QTextCursor.End)
            # Use a slight top margin for continuous flow
            self.activity.insertHtml(f"<div style='color:{color}; font-size:14px; line-height:1.55; white-space:pre-wrap; margin-top:10px;'>{formatted_text}</div>")
        else:
            block = f"""
            <table width='100%' cellspacing='0' cellpadding='0' style='margin-bottom:12px;'>
              <tr>
                <td style='background:{card_bg}; border-radius:12px; padding:14px 16px; border: 1px solid rgba(255,255,255,0.05);'>
                  <div style='margin-bottom:8px;'>
                    <span style='background:{badge_bg}; color:{color}; border-radius:6px; padding:3px 8px; font-size:10px; font-weight:800; letter-spacing:0.5px;'>{badge.upper()}</span>
                  </div>
                  <div style='color:{color}; font-size:14px; line-height:1.55; white-space:pre-wrap;'>{formatted_text}</div>
                </td>
              </tr>
            </table>
            """
            self.activity.moveCursor(QTextCursor.End)
            self.activity.insertHtml(block)
            self.activity.insertHtml("<br>")
            self.last_card_id = True

        self.last_kind = kind
        self.activity.moveCursor(QTextCursor.End)

    def update_screenshot(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.screenshot_label.setText("Screenshot unavailable")
            return
        scaled = pixmap.scaled(
            self.screenshot_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.screenshot_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if os.path.exists(SCREENSHOT_PATH):
            self.update_screenshot(SCREENSHOT_PATH)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UnibrowseApp()
    window.show()
    sys.exit(app.exec())
