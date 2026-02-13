"""
Onboarding Dashboard - Entry point for DEC HMI Application.
Displays three application tiles; clicking one launches the corresponding sub-application.
"""
import os
import sys
import subprocess

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QApplication, QScrollArea, QSizePolicy, QProgressBar
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QFont, QBrush

from shared.title_bar import CustomTitleBar, get_app_icon, get_project_root


def _project_root():
    """Return the project root directory (or bundle root when frozen)."""
    return get_project_root()


def _tile_image(path: str, fallback_color: str, size: int = 120) -> QPixmap:
    """Load tile image from path, or create a colored placeholder."""
    to_try = [path] if path else []
    if path and not os.path.isfile(path):
        base, ext = os.path.splitext(path)
        to_try = [path, f"{base}.png", f"{base}.jpg", f"{base}.jpeg"]
    for p in to_try:
        if p and os.path.isfile(p):
            pix = QPixmap(p)
            if not pix.isNull():
                return pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    # Fallback: draw a colored square
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(fallback_color)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, size - 8, size - 8, 8, 8)
    painter.end()
    return pix


class DashboardTile(QFrame):
    """Clickable tile for the onboarding dashboard."""

    def __init__(self, title: str, description: str, image_path: str, fallback_color: str, app_module: str, display_name: str, dashboard, parent=None):
        super().__init__(parent)
        self._app_module = app_module
        self._display_name = display_name
        self._dashboard = dashboard
        self._title = title
        self._description = description
        self._image_path = image_path
        self._fallback_color = fallback_color
        self._is_loading = False
        self._is_running = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(280, 320)
        self.setStyleSheet("""
            DashboardTile {
                background-color: #2d2d30;
                border: 1px solid #3e3e42;
                border-radius: 12px;
            }
            DashboardTile:hover {
                background-color: #3e3e42;
                border-color: #007ACC;
            }
            DashboardTile[disabled="true"] {
                background-color: #252526;
                border-color: #555555;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Image
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setPixmap(_tile_image(image_path, fallback_color))
        self.img_label.setFixedHeight(120)
        layout.addWidget(self.img_label)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold;")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        # Description
        self.desc_label = QLabel(description)
        self.desc_label.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        self.desc_label.setWordWrap(True)
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.desc_label.setMinimumHeight(60)
        layout.addWidget(self.desc_label, 1)

        # Status label (Loading.. / Running..)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Loading overlay (stacked on top of tile)
        self._loading_overlay = QWidget(self)
        self._loading_overlay.setStyleSheet("background-color: rgba(30,30,30,0.9); border-radius: 12px;")
        self._loading_overlay.hide()
        overlay_layout = QVBoxLayout(self._loading_overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_text = QLabel("Loading...")
        loading_text.setStyleSheet("color: #ffffff; font-size: 16px;")
        overlay_layout.addWidget(loading_text)
        self._loading_spinner = QProgressBar()
        self._loading_spinner.setRange(0, 0)  # Indeterminate
        self._loading_spinner.setFixedWidth(120)
        self._loading_spinner.setStyleSheet("""
            QProgressBar { background-color: #3e3e42; border-radius: 4px; }
            QProgressBar::chunk { background-color: #007ACC; border-radius: 4px; }
        """)
        overlay_layout.addWidget(self._loading_spinner, 0, Qt.AlignmentFlag.AlignHCenter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._loading_overlay.setGeometry(self.rect())
        self._loading_overlay.raise_()

    def set_loading(self, loading: bool):
        self._is_loading = loading
        self._loading_overlay.setGeometry(self.rect())
        self._loading_overlay.setVisible(loading)
        if loading:
            self._loading_overlay.raise_()
            self.setCursor(Qt.CursorShape.WaitCursor)

    def set_running(self, running: bool):
        self._is_running = running
        self.setProperty("disabled", running)
        self.style().unpolish(self)
        self.style().polish(self)
        if running:
            self.status_label.setText(f"{self._display_name} - Running..")
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold;")
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
            self.setEnabled(False)
        else:
            self.status_label.setText("")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setEnabled(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._is_loading and not self._is_running:
            self._launch_app()
        super().mousePressEvent(event)

    def _launch_app(self):
        """Launch the sub-application (in-process when frozen, subprocess when running from source)."""
        if self._dashboard.is_app_running(self._app_module):
            return
        self.set_loading(True)
        QTimer.singleShot(50, lambda: self._do_launch())

    def _do_launch(self):
        """Perform the actual launch (called after UI has shown loading)."""
        root = _project_root()
        is_frozen = getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")

        if is_frozen:
            self._launch_in_process(root)
        else:
            self._launch_subprocess(root)

    def _launch_subprocess(self, root):
        """Launch in new process (development)."""
        python_exe = sys.executable
        if self._app_module == "monitoring":
            script = os.path.join(root, "monitoring", "main.py")
        elif self._app_module == "step7_exchange":
            script = os.path.join(root, "step7_exchange", "main.py")
        elif self._app_module == "st_block":
            script = os.path.join(root, "st_block", "main.py")
        else:
            self.set_loading(False)
            return
        if os.path.isfile(script):
            proc = subprocess.Popen([python_exe, script], cwd=root)
            self._dashboard.on_app_launched(self._app_module, self, process=proc)
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Not Found", f"Application script not found:\n{script}")
            self.set_loading(False)

    def _launch_in_process(self, root):
        """Launch sub-app in the same process (for frozen builds)."""
        from PySide6.QtWidgets import QMessageBox
        try:
            win = None
            if self._app_module == "monitoring":
                mon_dir = os.path.join(root, "monitoring")
                if mon_dir not in sys.path:
                    sys.path.insert(0, mon_dir)
                _orig_cwd = os.getcwd()
                os.chdir(mon_dir)
                try:
                    from main_window import MainWindow
                    win = MainWindow()
                    win.show()
                finally:
                    os.chdir(_orig_cwd)
            elif self._app_module == "step7_exchange":
                st7_dir = os.path.join(root, "step7_exchange")
                if st7_dir not in sys.path:
                    sys.path.insert(0, st7_dir)
                from main import Step7ExchangeWindow
                win = Step7ExchangeWindow()
                win.show()
            elif self._app_module == "st_block":
                st_dir = os.path.join(root, "st_block")
                if st_dir not in sys.path:
                    sys.path.insert(0, st_dir)
                from main import STBlockWindow
                win = STBlockWindow()
                win.show()
            self._dashboard.on_app_launched(self._app_module, self, window=win)
        except Exception as e:
            QMessageBox.warning(self, "Launch Error", str(e))
            self.set_loading(False)


class OnboardingDashboard(QMainWindow):
    """Main onboarding dashboard window with three application tiles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dec S&T - Application Launcher")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        icon = get_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setMinimumSize(700, 500)
        self.resize(900, 550)
        self.setStyleSheet("QMainWindow { background-color: #1e1e1e; }")

        # Track open apps: module -> {tile, window or process}
        self._open_apps = {}
        self._process_check_timer = QTimer(self)
        self._process_check_timer.timeout.connect(self._check_processes)
        self._process_check_timer.start(1000)

        # Root layout: title bar + content
        root = QWidget()
        root.setStyleSheet("QWidget#_rootWidget { border: 1px solid #3e3e42; }")
        root.setObjectName("_rootWidget")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(1, 0, 1, 1)
        root_layout.setSpacing(0)

        # Generic CustomTitleBar (icon, title, no menu, window controls)
        self._title_bar = CustomTitleBar(
            self,
            title="Dec S&T Application Suite",
            show_menu_bar=False,
        )
        root_layout.addWidget(self._title_bar)

        # Content
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(40, 40, 40, 40)

        # Subtitle (title is in CustomTitleBar)
        subtitle = QLabel("Select an application to launch")
        subtitle.setStyleSheet("color: #808080; font-size: 14px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(30)

        # Tiles grid
        proj_root = _project_root()
        images_dir = os.path.join(proj_root, "Images")

        tiles_config = [
            {
                "title": "Monitoring",
                "display_name": "Monitoring",
                "description": "Real-time PLC monitoring, data recording, and analytics. Connect to Snap7/ADS, plot variables, and analyze trends.",
                "image": os.path.join(images_dir, "DEC_Monitoring.png"),
                "color": "#007ACC",
                "module": "monitoring",
            },
            {
                "title": "Step7 Exchange Blocks Generation",
                "display_name": "Step7 Exchange",
                "description": "Generate Siemens Step7 exchange blocks from variable definitions and configuration.",
                "image": os.path.join(images_dir, "DEC_Exchange.png"),
                "color": "#4CAF50",
                "module": "step7_exchange",
            },
            {
                "title": "S&T Block Generation",
                "display_name": "S&T Block",
                "description": "Generate S&T blocks for process control and automation configurations.",
                "image": os.path.join(images_dir, "DEC_S_T_BlockConfig.png"),
                "color": "#9C27B0",
                "module": "st_block",
            },
        ]

        grid = QGridLayout()
        grid.setSpacing(24)  # Padding between the 3 dashboards
        for i, t in enumerate(tiles_config):
            tile = DashboardTile(
                title=t["title"],
                description=t["description"],
                image_path=t["image"],
                fallback_color=t["color"],
                app_module=t["module"],
                display_name=t["display_name"],
                dashboard=self,
            )
            grid.addWidget(tile, 0, i)
        layout.addLayout(grid, 1)

        # Status bar: "Monitoring - Running.." when an app is open
        self._status_bar = QLabel("")
        self._status_bar.setStyleSheet("color: #4CAF50; font-size: 12px;")
        self._status_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_bar)

        root_layout.addWidget(central, 1)
        self.setCentralWidget(root)

    def is_app_running(self, module: str) -> bool:
        """Return True if this specific app is already running (one instance per tile)."""
        if module not in self._open_apps:
            return False
        entry = self._open_apps[module]
        if "window" in entry and entry["window"] is not None:
            return entry["window"].isVisible()
        if "process" in entry and entry["process"] is not None:
            return entry["process"].poll() is None
        return False

    def on_app_launched(self, module: str, tile, window=None, process=None):
        """Called when an app has been launched (window shown or process started)."""
        tile.set_loading(False)
        tile.set_running(True)
        self._open_apps[module] = {"tile": tile, "window": window, "process": process}
        self._update_status_bar()
        if window is not None:
            try:
                window.destroyed.connect(lambda: self._on_window_closed(module))
            except Exception:
                pass

    def _update_status_bar(self):
        """Update status bar to show all running apps."""
        running = [
            entry["tile"]._display_name
            for entry in self._open_apps.values()
            if self._is_entry_running(entry)
        ]
        if running:
            self._status_bar.setText(" • ".join(running) + " - Running..")
            self._status_bar.setStyleSheet("color: #4CAF50; font-size: 12px;")
        else:
            self._status_bar.setText("")

    def _is_entry_running(self, entry) -> bool:
        if "window" in entry and entry["window"] is not None:
            return entry["window"].isVisible()
        if "process" in entry and entry["process"] is not None:
            return entry["process"].poll() is None
        return False

    def _on_window_closed(self, module: str):
        """Called when an in-process window is destroyed."""
        self._on_app_closed(module)

    def _check_processes(self):
        """Poll subprocesses to see if they exited."""
        for module in list(self._open_apps.keys()):
            entry = self._open_apps.get(module)
            if not entry or "process" not in entry or entry["process"] is None:
                continue
            proc = entry["process"]
            if proc.poll() is not None:
                self._on_app_closed(module)

    def _on_app_closed(self, module: str):
        """Re-enable only this tile when its app is closed."""
        if module not in self._open_apps:
            return
        entry = self._open_apps.pop(module)
        tile = entry.get("tile")
        if tile:
            tile.set_running(False)
        self._update_status_bar()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OnboardingDashboard()
    window.show()
    sys.exit(app.exec())
