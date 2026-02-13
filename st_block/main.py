"""
S&T Block Generation - Sub-application.
Generates S&T blocks for process control and automation configurations.
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


class STBlockWindow(QMainWindow):
    """Placeholder window for S&T block generation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("S&T Block Generation")
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
            title="S&T Block Generation",
            show_menu_bar=False,
        )
        root_layout.addWidget(self._title_bar)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addStretch()
        title = QLabel("S&T Block Generation")
        title.setStyleSheet("color: #ffffff; font-size: 24px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        desc = QLabel("This application will generate S&T blocks for process control and automation configurations.\n\n(Placeholder - to be implemented)")
        desc.setStyleSheet("color: #b0b0b0; font-size: 14px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addStretch()

        root_layout.addWidget(central, 1)
        self.setCentralWidget(root)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = STBlockWindow()
    window.show()
    sys.exit(app.exec())
