"""
Generic CustomTitleBar for DEC HMI applications.
Provides consistent icon, colors, and window controls across monitoring, step7_exchange, st_block, and onboarding.
"""
import os
import sys

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QMenuBar, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap


# ── Project root (for icon loading) ────────────────────────────────────────

def _project_root():
    """Return project root (or bundle root when frozen)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    # This file is in shared/, so project root is parent of shared/
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_project_root():
    """Return project root. Reusable across all sub-apps."""
    return _project_root()


def get_app_icon():
    """Load DEC application icon from Images folder. Reusable across all sub-apps."""
    base = _project_root()
    dec_group = os.path.join(base, "Images", "Dec Group_bleu_noir_transparent.png")
    if os.path.isfile(dec_group):
        pix = QPixmap(dec_group)
        if not pix.isNull():
            icon = QIcon()
            for size in (16, 24, 32, 48, 256):
                scaled = pix.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                icon.addPixmap(scaled)
            return icon
    dec_logo = os.path.join(base, "Images", "Dec True end-to-end final white_small.png")
    if os.path.isfile(dec_logo):
        icon = QIcon(dec_logo)
        if not icon.isNull():
            return icon
    for name in ("app_icon.ico", "app_icon.png", "icon.ico"):
        for folder in (base, os.path.join(base, "assets")):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                icon = QIcon(path)
                if not icon.isNull():
                    return icon
    return QIcon()


# ── Title bar colors (dark theme default) ──────────────────────────────────

TITLE_BAR_BG_DARK = "#1e1e1e"
TITLE_BAR_BG_LIGHT = "#f0f0f0"
TITLE_BAR_FG_DARK = "#cccccc"
TITLE_BAR_FG_LIGHT = "#333333"
MENU_HOVER_DARK = "#3e3e42"
MENU_HOVER_LIGHT = "#d0d0d0"


class CustomTitleBar(QWidget):
    """
    Generic custom title bar: icon, optional title text, optional menu bar, window controls.
    Use show_menu_bar=True for Monitoring (embeds QMenuBar); False for other apps.
    """

    def __init__(
        self,
        parent,
        title: str = "",
        icon=None,
        show_menu_bar: bool = False,
        background_color: str = TITLE_BAR_BG_DARK,
        show_window_controls: bool = True,
    ):
        super().__init__(parent)
        self._parent = parent
        self._drag_pos = None
        self._background_color = background_color
        self.setFixedHeight(32)
        self.setStyleSheet(f"background-color: {background_color};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(0)

        # App icon
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        _icon = icon if icon is not None else get_app_icon()
        if not _icon.isNull():
            pix = _icon.pixmap(16, 16)
            self.icon_label.setPixmap(pix)
        layout.addWidget(self.icon_label)
        layout.addSpacing(10)

        # Optional title text (when no menu bar)
        self.menu_bar = None
        if show_menu_bar:
            self.menu_bar = QMenuBar()
            self.menu_bar.setStyleSheet(self._menu_bar_stylesheet(background_color))
            self.menu_bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            layout.addWidget(self.menu_bar)
        elif title:
            title_label = QLabel(title)
            title_label.setStyleSheet("color: #cccccc; font-size: 12px; background: transparent;")
            title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(title_label)

        # Draggable spacer
        self._drag_spacer = QLabel()
        self._drag_spacer.setStyleSheet("background: transparent;")
        self._drag_spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._drag_spacer, 1)

        # Window control buttons
        if show_window_controls:
            btn_style_normal = """
                QPushButton {
                    background-color: transparent; color: #999999; border: none;
                    font-family: "Segoe MDL2 Assets"; font-size: 10px;
                    padding: 0px; min-width: 46px; min-height: 32px;
                }
                QPushButton:hover { background-color: #3e3e42; color: #ffffff; }
            """
            btn_style_close = """
                QPushButton {
                    background-color: transparent; color: #999999; border: none;
                    font-family: "Segoe MDL2 Assets"; font-size: 10px;
                    padding: 0px; min-width: 46px; min-height: 32px;
                }
                QPushButton:hover { background-color: #e81123; color: #ffffff; }
            """
            self.btn_minimize = QPushButton("\uE921")
            self.btn_minimize.setStyleSheet(btn_style_normal)
            self.btn_minimize.clicked.connect(parent.showMinimized)

            self.btn_maximize = QPushButton("\uE922")
            self.btn_maximize.setStyleSheet(btn_style_normal)
            self.btn_maximize.clicked.connect(self._toggle_maximize)

            self.btn_close = QPushButton("\uE8BB")
            self.btn_close.setStyleSheet(btn_style_close)
            self.btn_close.clicked.connect(parent.close)

            layout.addWidget(self.btn_minimize)
            layout.addWidget(self.btn_maximize)
            layout.addWidget(self.btn_close)
        else:
            self.btn_minimize = self.btn_maximize = self.btn_close = None

    def _menu_bar_stylesheet(self, bg_color: str) -> str:
        is_dark = bg_color == TITLE_BAR_BG_DARK or bg_color.lower() in ("#1e1e1e", "#252526")
        fg = TITLE_BAR_FG_DARK if is_dark else TITLE_BAR_FG_LIGHT
        hover = MENU_HOVER_DARK if is_dark else MENU_HOVER_LIGHT
        return f"""
            QMenuBar {{ background-color: transparent; color: {fg}; border: none; font-size: 12px; }}
            QMenuBar::item {{ background-color: transparent; padding: 6px 10px; border-radius: 3px; }}
            QMenuBar::item:selected {{ background-color: {hover}; color: {'#ffffff' if is_dark else '#333333'}; }}
            QMenuBar::item:pressed {{ background-color: #007ACC; color: white; }}
        """

    def _toggle_maximize(self):
        if self._parent.isMaximized():
            self._parent.showNormal()
            if self.btn_maximize:
                self.btn_maximize.setText("\uE922")
        else:
            self._parent.showMaximized()
            if self.btn_maximize:
                self.btn_maximize.setText("\uE923")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._parent.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()

    def apply_theme(self, mode: str = "dark"):
        """Apply dark or light theme to title bar and menu."""
        if mode == "light":
            bg = TITLE_BAR_BG_LIGHT
            fg = TITLE_BAR_FG_LIGHT
            menu_hover = MENU_HOVER_LIGHT
            menu_fg = "#333333"
        else:
            bg = TITLE_BAR_BG_DARK
            fg = TITLE_BAR_FG_DARK
            menu_hover = MENU_HOVER_DARK
            menu_fg = "#ffffff"
        self._background_color = bg
        self.setStyleSheet(f"background-color: {bg};")
        if self.menu_bar:
            self.menu_bar.setStyleSheet(f"""
                QMenuBar {{ background-color: transparent; color: {fg}; border: none; font-size: 12px; }}
                QMenuBar::item {{ background-color: transparent; padding: 6px 10px; border-radius: 3px; }}
                QMenuBar::item:selected {{ background-color: {menu_hover}; color: {menu_fg}; }}
                QMenuBar::item:pressed {{ background-color: #007ACC; color: white; }}
            """)
