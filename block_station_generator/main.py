"""
Block/Station Generator - Sub-application.
Generates or modifies blocks and stations. A station is a system; a block is a subsystem.
Focus: stepper part (GRAFCET) which works in cases within function blocks.
"""
import sys
import os

# Ensure project root is on path for shared module
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QStackedWidget, QFrame,
    QComboBox, QSplitter, QPlainTextEdit, QPushButton, QFileDialog,
    QMessageBox, QScrollArea
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont

from shared.title_bar import CustomTitleBar, get_app_icon
from shared.frameless_resize import FramelessResizeMixin

from block_station_generator.core.template_loader import list_templates
from block_station_generator.views.grafcet_generator import GrafcetGeneratorView
from block_station_generator.views.decorations_generator import DecorationsGeneratorView
from block_station_generator.views.io_generator import IOGeneratorView
from block_station_generator.views.hmi_generator import HMIGeneratorView


MENU_ITEMS = [
    ("Grafcet Generation", "grafcet", "Design steps and transitions for the stepper"),
    ("Decorations", "decorations", "Child instances, multi-instances"),
    ("Inputs & Outputs", "io", "Block inputs and outputs"),
    ("HMI", "hmi", "HMI UDT fields and transfer"),
]


class BlockStationGeneratorWindow(FramelessResizeMixin, QMainWindow):
    """Window for block/station generation with menubar and generation views."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Block/Station Generator")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        icon = get_app_icon()
        if icon and not icon.isNull():
            self.setWindowIcon(icon)
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)
        self.setStyleSheet("QMainWindow { background-color: #1e1e1e; }")

        # Root: title bar + content
        root = QWidget()
        root.setStyleSheet("QWidget#_rootWidget { border: 1px solid #3e3e42; }")
        root.setObjectName("_rootWidget")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(1, 0, 1, 1)
        root_layout.setSpacing(0)

        self._title_bar = CustomTitleBar(
            self,
            title="Block/Station Generator",
            show_menu_bar=False,
        )
        root_layout.addWidget(self._title_bar)

        # Main content: left menu + right area
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Left sidebar: template selector + menu
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("""
            QFrame { background: #252526; border-right: 1px solid #3e3e42; }
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(12)

        sidebar_layout.addWidget(QLabel("Template"))
        self._template_combo = QComboBox()
        self._template_combo.setStyleSheet("""
            QComboBox { background: #3c3c3c; color: #d4d4d4; padding: 6px; }
        """)
        for t in list_templates():
            self._template_combo.addItem(t["name"], t)
        sidebar_layout.addWidget(self._template_combo)

        sidebar_layout.addWidget(QLabel("Generation"))
        self._menu_list = QListWidget()
        self._menu_list.setStyleSheet("""
            QListWidget { background: #252526; color: #d4d4d4; border: none; }
            QListWidget::item { padding: 8px 12px; }
            QListWidget::item:selected { background: #0e639c; }
            QListWidget::item:hover { background: #2d2d30; }
        """)
        for title, key, desc in MENU_ITEMS:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._menu_list.addItem(item)
        sidebar_layout.addWidget(self._menu_list, 1)

        content_layout.addWidget(sidebar)

        # Right: stacked views (create before connecting menu signal)
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: #1e1e1e;")

        self._grafcet_view = GrafcetGeneratorView()
        self._decorations_view = DecorationsGeneratorView()
        self._io_view = IOGeneratorView()
        self._hmi_view = HMIGeneratorView()

        self._stack.addWidget(self._grafcet_view)
        self._stack.addWidget(self._decorations_view)
        self._stack.addWidget(self._io_view)
        self._stack.addWidget(self._hmi_view)

        content_layout.addWidget(self._stack, 1)

        self._menu_list.currentRowChanged.connect(self._on_menu_changed)
        self._menu_list.setCurrentRow(0)

        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def _on_menu_changed(self, row: int):
        if row >= 0:
            self._stack.setCurrentIndex(row)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BlockStationGeneratorWindow()
    window.show()
    sys.exit(app.exec())
