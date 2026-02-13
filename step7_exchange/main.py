"""
Step7 Exchange Blocks Generation - Sub-application.
Generates Siemens Step7 exchange blocks from variable definitions and configuration.
"""
import sys
import os

# Ensure project root is on path for shared module
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QGroupBox, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, QUrl, QSettings
from PySide6.QtGui import QDesktopServices

from shared.title_bar import CustomTitleBar, get_app_icon


def _default_exchange_path():
    """Default path to exchange_variables.csv (monitoring/external)."""
    ext = os.path.join(os.path.dirname(os.path.dirname(__file__)), "monitoring", "external")
    disc = None
    try:
        from monitoring.external.variable_loader import discover_csv_files
        disc, _ = discover_csv_files(ext)
    except Exception:
        pass
    return disc or os.path.join(ext, "exchange_variables.csv")


def _default_recipe_path():
    """Default path to recipe_variables.csv."""
    ext = os.path.join(os.path.dirname(os.path.dirname(__file__)), "monitoring", "external")
    disc = None
    try:
        from monitoring.external.variable_loader import discover_csv_files
        _, disc = discover_csv_files(ext)
    except Exception:
        pass
    return disc or os.path.join(ext, "recipe_variables.csv")


def _default_output_dir():
    """Default output folder: monitoring/external/Output."""
    ext = os.path.join(os.path.dirname(os.path.dirname(__file__)), "monitoring", "external")
    return os.path.join(ext, "Output")


def _default_output_filename():
    """Default output filename: Exchange_Blocks.scl."""
    return "Exchange_Blocks.scl"


def _ensure_scl_ext(name: str) -> str:
    """Ensure filename ends with .scl (add if missing)."""
    if not name or not name.strip():
        return _default_output_filename()
    name = name.strip()
    if not name.lower().endswith(".scl"):
        return name + ".scl"
    return name


# Dark theme stylesheet for all message dialogs (matches main window)
_MSG_STYLE = """
    QMessageBox {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #0f3460);
        color: #c0c0c0;
    }
    QMessageBox QLabel { color: #c0c0c0; }
    QPushButton {
        background-color: #2d2d30;
        color: #e0e0e0;
        border: 1px solid #555;
        border-radius: 4px;
        padding: 6px 12px;
    }
    QPushButton:hover {
        background-color: #3e3e42;
        border-color: #007ACC;
        color: #ffffff;
    }
"""


def _dark_message(parent, title: str, text: str, icon=QMessageBox.Icon.Information, buttons=QMessageBox.StandardButton.Ok):
    """Show a dark-themed message box."""
    mb = QMessageBox(parent)
    mb.setWindowTitle(title)
    mb.setText(text)
    mb.setIcon(icon)
    mb.setStandardButtons(buttons)
    mb.setStyleSheet(_MSG_STYLE)
    return mb.exec()


class Step7ExchangeWindow(QMainWindow):
    """Window for Step7 Exchange blocks generation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Step7 Exchange Blocks Generation")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        icon = get_app_icon()
        if icon and not icon.isNull():
            self.setWindowIcon(icon)
        self.setMinimumSize(650, 500)
        self.resize(800, 550)

        # Dark theme based on monitoring Help->About (gradient, accent #007ACC)
        self._apply_theme()

        # Paths
        s = QSettings("DecAutomation", "Studio")
        self._exchange_path = s.value("step7_exchange_path", _default_exchange_path()) or _default_exchange_path()
        self._recipe_path = s.value("step7_recipe_path", _default_recipe_path()) or _default_recipe_path()
        self._output_dir = s.value("step7_output_dir", "") or _default_output_dir()
        self._output_filename = s.value("step7_output_filename", "") or _default_output_filename()

        # Root: title bar + content
        root = QWidget()
        root.setObjectName("_rootWidget")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(1, 0, 1, 1)
        root_layout.setSpacing(0)

        self._title_bar = CustomTitleBar(
            self,
            title="Step7 Exchange Blocks Generation",
            show_menu_bar=False,
        )
        root_layout.addWidget(self._title_bar)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(16)

        # Title
        title = QLabel("Step7 Exchange Blocks Generation")
        title.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: bold; font-family: 'Segoe UI', Arial, sans-serif;")
        layout.addWidget(title)

        desc = QLabel(
            "Generate Siemens Step7 DB and FC blocks from exchange_variables.csv and recipe_variables.csv."
        )
        desc.setStyleSheet("color: #7eb8da; font-size: 12px; font-family: 'Segoe UI', Arial, sans-serif;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Input files group
        grp = QGroupBox("Input files")
        grp_layout = QVBoxLayout(grp)

        self._exchange_edit = QLineEdit()
        self._exchange_edit.setReadOnly(True)
        self._exchange_edit.setText(self._exchange_path)
        self._browse_exchange_btn = QPushButton("Browse…")
        self._browse_exchange_btn.clicked.connect(self._browse_exchange)
        ex_row = QHBoxLayout()
        ex_row.addWidget(QLabel("Exchange CSV:"))
        ex_row.addWidget(self._exchange_edit, 1)
        ex_row.addWidget(self._browse_exchange_btn)
        grp_layout.addLayout(ex_row)

        self._recipe_edit = QLineEdit()
        self._recipe_edit.setReadOnly(True)
        self._recipe_edit.setText(self._recipe_path)
        self._browse_recipe_btn = QPushButton("Browse…")
        self._browse_recipe_btn.clicked.connect(self._browse_recipe)
        rec_row = QHBoxLayout()
        rec_row.addWidget(QLabel("Recipe CSV:"))
        rec_row.addWidget(self._recipe_edit, 1)
        rec_row.addWidget(self._browse_recipe_btn)
        grp_layout.addLayout(rec_row)

        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.setPlaceholderText("Folder path (default: external/Output)")
        self._output_dir_edit.setText(self._output_dir)
        self._browse_output_dir_btn = QPushButton("Browse…")
        self._browse_output_dir_btn.clicked.connect(self._browse_output_dir)
        out_dir_row = QHBoxLayout()
        out_dir_row.addWidget(QLabel("Output path:"))
        out_dir_row.addWidget(self._output_dir_edit, 1)
        out_dir_row.addWidget(self._browse_output_dir_btn)
        grp_layout.addLayout(out_dir_row)

        self._output_filename_edit = QLineEdit()
        self._output_filename_edit.setPlaceholderText("Exchange_Blocks.scl")
        self._output_filename_edit.setText(self._output_filename)
        out_name_row = QHBoxLayout()
        out_name_row.addWidget(QLabel("File name:"))
        out_name_row.addWidget(self._output_filename_edit, 1)
        grp_layout.addLayout(out_name_row)

        # Open folder button (opens folder containing CSVs and output)
        self._open_folder_btn = QPushButton("Open folder")
        self._open_folder_btn.setToolTip("Open the folder containing exchange_variables_DBxx.csv, recipe_variables_DBxx.csv and output SCL")
        self._open_folder_btn.clicked.connect(self._open_output_folder)
        folder_row = QHBoxLayout()
        folder_row.addStretch()
        folder_row.addWidget(self._open_folder_btn)
        grp_layout.addLayout(folder_row)

        layout.addWidget(grp)

        # Generate button (primary action - accent color like About dialog)
        self._generate_btn = QPushButton("Generate Exchange Blocks")
        self._generate_btn.setObjectName("generateBtn")
        self._generate_btn.setStyleSheet("""
            QPushButton#generateBtn {
                background-color: #007ACC;
                color: white;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
            }
            QPushButton#generateBtn:hover {
                background-color: #0098FF;
            }
            QPushButton#generateBtn:pressed {
                background-color: #005a9e;
            }
        """)
        self._generate_btn.clicked.connect(self._generate)
        layout.addWidget(self._generate_btn)

        # Status
        self._status = QLabel("")
        self._status.setStyleSheet("color: #7eb8da; font-size: 11px;")
        layout.addWidget(self._status)

        layout.addStretch()
        scroll.setWidget(central)
        root_layout.addWidget(scroll, 1)
        self.setCentralWidget(root)

    def _apply_theme(self):
        """Apply dark theme based on monitoring Help->About (gradient, #007ACC accent)."""
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #0f3460);
            }
            QWidget#_rootWidget {
                background: transparent;
                border: 1px solid #007ACC;
            }
            QScrollArea, QScrollArea::viewport, QScrollArea > QWidget > QWidget {
                background: transparent;
                border: none;
            }
            QLabel {
                color: #c0c0c0;
                background: transparent;
            }
            QGroupBox {
                color: #7eb8da;
                font-weight: bold;
                border: 1px solid #007ACC;
                border-radius: 8px;
                margin-top: 12px;
                padding: 16px 12px 8px 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: #7eb8da;
            }
            QLineEdit {
                background-color: #2d2d30;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 8px;
                selection-background-color: #007ACC;
            }
            QLineEdit:focus {
                border-color: #007ACC;
            }
            QPushButton {
                background-color: #2d2d30;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #3e3e42;
                border-color: #007ACC;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #007ACC;
                color: white;
            }
        """)

    def _browse_exchange(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select exchange variables CSV", self._exchange_path or "",
            "CSV (*.csv);;All files (*)"
        )
        if path:
            self._exchange_path = os.path.normpath(path)
            self._exchange_edit.setText(self._exchange_path)
            self._save_paths()

    def _browse_recipe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select recipe variables CSV", self._recipe_path or "",
            "CSV (*.csv);;All files (*)"
        )
        if path:
            self._recipe_path = os.path.normpath(path)
            self._recipe_edit.setText(self._recipe_path)
            self._save_paths()

    def _get_output_full_path(self) -> str:
        """Build full output path from dir + filename (ensures .scl)."""
        d = (self._output_dir_edit.text() or "").strip() or _default_output_dir()
        f = _ensure_scl_ext(self._output_filename_edit.text() or "")
        return os.path.normpath(os.path.join(d, f))

    def _open_output_folder(self):
        """Open the folder containing exchange_variables_DBxx.csv, recipe_variables and output SCL in the system file manager."""
        folder = (self._output_dir_edit.text() or "").strip() or _default_output_dir()
        ex = self._exchange_path or ""
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.normpath(folder)))
        elif ex:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.normpath(os.path.dirname(ex))))
        else:
            _dark_message(self, "Open folder", "Select an output path or exchange CSV first, then use Open folder.")

    def _browse_output_dir(self):
        start = (self._output_dir_edit.text() or "").strip() or _default_output_dir()
        folder = QFileDialog.getExistingDirectory(self, "Select output folder", start)
        if folder:
            self._output_dir = os.path.normpath(folder)
            self._output_dir_edit.setText(self._output_dir)
            self._save_paths()

    def _save_paths(self):
        s = QSettings("DecAutomation", "Studio")
        s.setValue("step7_exchange_path", self._exchange_path)
        s.setValue("step7_recipe_path", self._recipe_path)
        s.setValue("step7_output_dir", (self._output_dir_edit.text() or "").strip() or _default_output_dir())
        s.setValue("step7_output_filename", _ensure_scl_ext(self._output_filename_edit.text() or ""))

    def _generate(self):
        ex = self._exchange_path
        rec = self._recipe_path
        out = self._get_output_full_path()

        if not ex or not os.path.isfile(ex):
            self._status.setText("Error: Exchange variables CSV not found.")
            _dark_message(self, "Error", "Please select a valid exchange variables CSV file.", QMessageBox.Icon.Warning)
            return
        if not rec or not os.path.isfile(rec):
            self._status.setText("Error: Recipe variables CSV not found.")
            _dark_message(self, "Error", "Please select a valid recipe variables CSV file.", QMessageBox.Icon.Warning)
            return

        # Overwrite confirmation if file exists
        if os.path.isfile(out):
            mb = QMessageBox(self)
            mb.setWindowTitle("Overwrite?")
            mb.setText(f"The file already exists:\n{out}\n\nOverwrite?")
            mb.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            mb.setDefaultButton(QMessageBox.StandardButton.No)
            mb.setStyleSheet(_MSG_STYLE)
            if mb.exec() != QMessageBox.StandardButton.Yes:
                return

        try:
            from step7_exchange.generator import generate
            result = generate(exchange_csv=ex, recipe_csv=rec, output_path=out)
            self._status.setText(f"Generated: {result}")
            self._output_dir = os.path.dirname(result)
            self._output_filename = os.path.basename(result)
            self._output_dir_edit.setText(self._output_dir)
            self._output_filename_edit.setText(self._output_filename)
            self._save_paths()
            _dark_message(self, "Success", f"Exchange blocks generated successfully:\n{result}", QMessageBox.Icon.Information)
        except Exception as e:
            self._status.setText(f"Error: {e}")
            _dark_message(self, "Error", str(e), QMessageBox.Icon.Critical)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Step7ExchangeWindow()
    window.show()
    sys.exit(app.exec())
