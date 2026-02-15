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

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

from shared.title_bar import CustomTitleBar, get_app_icon
from shared.frameless_resize import FramelessResizeMixin


class BlockStationGeneratorWindow(FramelessResizeMixin, QMainWindow):
    """Window for block/station generation and modification."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Block/Station Generator")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        icon = get_app_icon()
        if icon and not icon.isNull():
            self.setWindowIcon(icon)
        self.setMinimumSize(600, 400)
        self.resize(800, 500)
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

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addStretch()
        title = QLabel("Block/Station Generator")
        title.setStyleSheet("color: #ffffff; font-size: 24px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        desc = QLabel(
            "Generate or modify blocks and stations. "
            "Stations are systems; blocks are subsystems. "
            "Focus: stepper (GRAFCET) in function blocks.\n\n"
            "Templates: Templates/Blocks and Templates/Stations\n\n"
            "(Placeholder - to be implemented)"
        )
        desc.setStyleSheet("color: #b0b0b0; font-size: 14px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addStretch()

        root_layout.addWidget(central, 1)
        self.setCentralWidget(root)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BlockStationGeneratorWindow()
    window.show()
    sys.exit(app.exec())
