import sys
import os
import json
import pathlib
import urllib.request
import urllib.error
import webbrowser

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QComboBox,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QMessageBox,
)


# -------------------------------------------------------
# Configuration paths (AppData on Windows, ~/.config else)
# -------------------------------------------------------

def get_config_dir() -> pathlib.Path:
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA")
        if base:
            return pathlib.Path(base) / "AtmoReleaseChecker"
    # Fallback for Linux/macOS
    base = os.path.expanduser("~/.config")
    return pathlib.Path(base) / "AtmoReleaseChecker"


CONFIG_DIR = get_config_dir()
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"


# -------------------------------------------------------
# Project definitions
# -------------------------------------------------------

PROJECTS = {
    "Atmosphere": {
        "key": "atmosphere",
        "api_url": "https://api.github.com/repos/Atmosphere-NX/Atmosphere/releases/latest",
        "page_url": "https://github.com/Atmosphere-NX/Atmosphere/releases/latest",
        "hos_support": "Latest supported HOS: 20.5.0 (Basic support)",
    },
    "Hekate": {
        "key": "hekate",
        "api_url": "https://api.github.com/repos/CTCaer/hekate/releases/latest",
        "page_url": "https://github.com/CTCaer/hekate/releases/latest",
        "hos_support": "Latest supported HOS: 20.5.0",
    },
}


# -------------------------------------------------------
# Config load / save
# -------------------------------------------------------

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {"local_versions": {}}
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if "local_versions" not in data:
            data["local_versions"] = {}
        return data
    except Exception:
        return {"local_versions": {}}


def save_config(config: dict) -> None:
    try:
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print("Error saving config:", e)


# -------------------------------------------------------
# GitHub fetcher (runs in QThread)
# -------------------------------------------------------

def fetch_latest_release(api_url: str) -> dict:
    """
    Fetch latest release info from GitHub API using stdlib only.
    Returns dict with keys: tag, name, body, html_url, published_at
    """
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "AtmoHekateChecker/1.0 (Python)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8")
        obj = json.loads(data)
        tag = (obj.get("tag_name") or "").strip()
        name = (obj.get("name") or "").strip()
        body = (obj.get("body") or "").strip()
        html_url = (obj.get("html_url") or "").strip()
        published_at = (obj.get("published_at") or "").strip()
        return {
            "tag": tag,
            "name": name,
            "body": body,
            "html_url": html_url,
            "published_at": published_at,
        }
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e}")
    except Exception as e:
        raise RuntimeError(f"Error: {e}")


class ReleaseFetcherThread(QThread):
    finished_ok = pyqtSignal(dict)
    finished_error = pyqtSignal(str)

    def __init__(self, api_url: str, parent=None):
        super().__init__(parent)
        self.api_url = api_url

    def run(self):
        try:
            info = fetch_latest_release(self.api_url)
            self.finished_ok.emit(info)
        except RuntimeError as e:
            self.finished_error.emit(str(e))


# -------------------------------------------------------
# Main Window
# -------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Atmosphere / Hekate Release Checker")
        self.resize(880, 540)

        # Data
        self.config = load_config()
        self.current_project_name = "Atmosphere"
        self.current_release_info = None
        self.fetch_thread: ReleaseFetcherThread | None = None

        # UI
        self._build_ui()
        self._apply_styles()

        # Initial state
        self.update_local_version_label()
        self.update_hos_support_label()

        # Auto-check on startup
        self.start_check()

    # ---------------- UI building -----------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Title
        title_label = QLabel("Atmosphere / Hekate Release Checker")
        title_font = QFont("Segoe UI", 17, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # Top info group
        info_group = QGroupBox("Release Info")
        info_layout = QGridLayout(info_group)
        info_layout.setVerticalSpacing(6)
        info_layout.setHorizontalSpacing(10)

        row = 0

        # Project selector
        lbl_project = QLabel("Project:")
        lbl_project.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        info_layout.addWidget(lbl_project, row, 0)

        self.project_combo = QComboBox()
        self.project_combo.addItems(PROJECTS.keys())
        self.project_combo.currentTextChanged.connect(self.on_project_changed)
        self.project_combo.setMinimumWidth(220)
        info_layout.addWidget(self.project_combo, row, 1, 1, 2)

        row += 1

        # Local version
        lbl_local = QLabel("Local version:")
        lbl_local.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        info_layout.addWidget(lbl_local, row, 0)

        self.local_value = QLabel("Not set")
        info_layout.addWidget(self.local_value, row, 1, 1, 2)

        row += 1

        # Latest version
        lbl_latest = QLabel("Latest on GitHub:")
        lbl_latest.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        info_layout.addWidget(lbl_latest, row, 0)

        self.latest_value = QLabel("Unknown")
        info_layout.addWidget(self.latest_value, row, 1, 1, 2)

        row += 1

        # HOS support
        lbl_hos = QLabel("HOS support:")
        lbl_hos.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        info_layout.addWidget(lbl_hos, row, 0)

        self.hos_value = QLabel("-")
        info_layout.addWidget(self.hos_value, row, 1, 1, 2)

        row += 1

        # Published
        lbl_pub = QLabel("Published:")
        lbl_pub.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        info_layout.addWidget(lbl_pub, row, 0)

        self.published_value = QLabel("-")
        info_layout.addWidget(self.published_value, row, 1, 1, 2)

        row += 1

        # Status
        lbl_status = QLabel("Status:")
        lbl_status.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        info_layout.addWidget(lbl_status, row, 0)

        self.status_value = QLabel("Idle")
        info_layout.addWidget(self.status_value, row, 1, 1, 2)

        main_layout.addWidget(info_group)

        # Buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_check = QPushButton("Check Now")
        self.btn_check.clicked.connect(self.start_check)
        btn_layout.addWidget(self.btn_check)

        self.btn_set_local = QPushButton("Set Local = Latest")
        self.btn_set_local.clicked.connect(self.set_local_to_latest)
        btn_layout.addWidget(self.btn_set_local)

        self.btn_open_page = QPushButton("Open GitHub Page")
        self.btn_open_page.clicked.connect(self.open_github_page)
        btn_layout.addWidget(self.btn_open_page)

        btn_layout.addStretch()

        self.btn_quit = QPushButton("Quit")
        self.btn_quit.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_quit)

        main_layout.addLayout(btn_layout)

        # Changelog
        changelog_group = QGroupBox("Changelog (Release Notes)")
        cl_layout = QVBoxLayout(changelog_group)
        self.changelog_edit = QTextEdit()
        self.changelog_edit.setReadOnly(True)
        self.changelog_edit.setFont(QFont("Consolas", 9))
        self.changelog_edit.setPlainText("No data yet. Press 'Check Now'.")
        cl_layout.addWidget(self.changelog_edit)
        main_layout.addWidget(changelog_group, 1)  # stretch

    def _apply_styles(self):
        # Dark, modern look
        self.setStyleSheet("""
            QMainWindow {
                background-color: #15171c;
            }
            QWidget {
                color: #f3f3f4;
                background-color: transparent;
                font-family: "Segoe UI", "Calibri", sans-serif;
            }
            QGroupBox {
                border: 1px solid #2c2f36;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 16px;
                background-color: #1b1e24;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                background-color: #15171c;
                color: #c7cad1;
                font-weight: bold;
                font-size: 10pt;
            }
            QLabel {
                font-size: 10pt;
                color: #e2e4ea;
            }
            QLabel#statusLabel {
                font-weight: bold;
            }
            QComboBox {
                background-color: #20232b;
                border: 1px solid #3a3f4b;
                border-radius: 6px;
                padding: 4px 8px;
                color: #f5f5f5;
                font-size: 9.5pt;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1f2229;
                color: #f5f5f5;
                selection-background-color: #2f80ed;
            }
            QPushButton {
                background-color: #252932;
                border: 1px solid #3b404d;
                border-radius: 6px;
                padding: 5px 12px;
                color: #f3f3f4;
                font-size: 9.5pt;
            }
            QPushButton:hover {
                background-color: #2f3440;
            }
            QPushButton:pressed {
                background-color: #232733;
            }
            QPushButton#dangerButton {
                background-color: #b33939;
                border-color: #d24f4f;
            }
            QPushButton#dangerButton:hover {
                background-color: #c44545;
            }
            QTextEdit {
                background-color: #0f1116;
                color: #e6e6e6;
                border-radius: 6px;
                border: 1px solid #31343f;
                padding: 6px;
            }
            QScrollBar:vertical {
                background: #101218;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #3b404d;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4c5262;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Give the Quit button a "danger" style
        self.btn_quit.setObjectName("dangerButton")

    # ---------------- Helpers -----------------

    def get_current_project_info(self) -> dict:
        name = self.current_project_name
        return PROJECTS[name]

    def get_local_version_for_project(self, project_key: str) -> str | None:
        return self.config.get("local_versions", {}).get(project_key)

    def set_local_version_for_project(self, project_key: str, version: str) -> None:
        if "local_versions" not in self.config:
            self.config["local_versions"] = {}
        self.config["local_versions"][project_key] = version
        save_config(self.config)

    def update_local_version_label(self):
        info = self.get_current_project_info()
        key = info["key"]
        local = self.get_local_version_for_project(key)
        self.local_value.setText(local if local else "Not set")

    def update_hos_support_label(self):
        info = self.get_current_project_info()
        self.hos_value.setText(info.get("hos_support", "-"))

    def set_changelog_text(self, text: str):
        self.changelog_edit.setPlainText(text)

    # ---------------- Events -----------------

    def on_project_changed(self, name: str):
        self.current_project_name = name
        self.update_local_version_label()
        self.update_hos_support_label()
        self.latest_value.setText("Unknown")
        self.published_value.setText("-")
        self.status_value.setText("Idle")
        self.set_changelog_text("No data for this project yet. Press 'Check Now'.")

    def start_check(self):
        if self.fetch_thread and self.fetch_thread.isRunning():
            return  # already running

        info = self.get_current_project_info()
        api_url = info["api_url"]

        self.status_value.setText("Checking...")
        self.btn_check.setEnabled(False)

        self.fetch_thread = ReleaseFetcherThread(api_url, self)
        self.fetch_thread.finished_ok.connect(self.on_fetch_success)
        self.fetch_thread.finished_error.connect(self.on_fetch_error)
        self.fetch_thread.start()

    def on_fetch_success(self, rel_info: dict):
        self.fetch_thread = None
        self.current_release_info = rel_info

        tag = rel_info.get("tag") or "Unknown"
        name = rel_info.get("name") or ""
        published = rel_info.get("published_at") or "-"
        body = rel_info.get("body") or ""

        self.latest_value.setText(tag)
        self.published_value.setText(published)

        header_lines = []
        if name:
            header_lines.append(f"Release: {name}")
        if tag:
            header_lines.append(f"Tag: {tag}")
        if published and published != "-":
            header_lines.append(f"Published: {published}")

        header = "\n".join(header_lines)
        if header:
            header += "\n\n" + "-" * 60 + "\n\n"

        self.set_changelog_text(header + body)

        # Compare with local
        info = self.get_current_project_info()
        key = info["key"]
        local = self.get_local_version_for_project(key)

        if not local:
            status = "Local version not set."
        else:
            if tag not in ("Unknown", ""):
                if tag != local:
                    status = f"New version available! ({tag})"
                    QMessageBox.information(
                        self,
                        "New Release Available",
                        f"Project: {self.current_project_name}\n"
                        f"Local: {local}\n"
                        f"Latest: {tag}",
                    )
                else:
                    status = "You are up to date."
            else:
                status = "Could not determine latest version."

        self.status_value.setText(status)
        self.btn_check.setEnabled(True)

    def on_fetch_error(self, msg: str):
        self.fetch_thread = None
        self.latest_value.setText("Error")
        self.published_value.setText("-")
        self.set_changelog_text("Error while fetching release info.")
        self.status_value.setText("Error while checking.")
        self.btn_check.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Failed to check latest release:\n{msg}")

    def set_local_to_latest(self):
        if not self.current_release_info:
            QMessageBox.warning(
                self,
                "Warning",
                "No latest release info yet.\nPress 'Check Now' first.",
            )
            return

        tag = self.current_release_info.get("tag") or ""
        if not tag or tag == "Unknown":
            QMessageBox.warning(
                self,
                "Warning",
                "Latest version is unknown. Cannot set local.",
            )
            return

        info = self.get_current_project_info()
        key = info["key"]
        self.set_local_version_for_project(key, tag)
        self.local_value.setText(tag)
        self.status_value.setText("Local version updated.")

    def open_github_page(self):
        info = self.get_current_project_info()
        url = info["page_url"]
        webbrowser.open(url)


# -------------------------------------------------------
# Main entry
# -------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
