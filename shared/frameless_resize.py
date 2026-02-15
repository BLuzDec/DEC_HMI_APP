"""
Frameless window edge/corner resize support for Windows.

When using Qt.FramelessWindowHint, the native window border is removed and
Windows no longer provides resize handles. This mixin:
1. Adds WS_THICKFRAME so the window can be resized by the system
2. Implements WM_NCHITTEST to define resize regions at edges/corners

Usage:
    class MyWindow(FramelessResizeMixin, QMainWindow):
        ...
"""
import sys


# Windows constants
GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WM_NCHITTEST = 0x0084
HTLEFT, HTRIGHT, HTTOP, HTBOTTOM = 10, 11, 12, 15
HTTOPLEFT, HTTOPRIGHT, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 16, 17
HTCAPTION = 2


class FramelessResizeMixin:
    """Mixin for QMainWindow/QWidget that enables edge/corner resize on frameless windows (Windows)."""

    _BORDER = 8  # pixels from edge that trigger resize
    _thickframe_applied = False

    def showEvent(self, event):
        """Add WS_THICKFRAME so Windows allows resizing (required for frameless windows)."""
        super().showEvent(event)
        if sys.platform == "win32" and not getattr(self, "_thickframe_applied", False):
            try:
                import ctypes
                from ctypes import wintypes
                hwnd = int(self.winId())
                if hwnd:
                    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                    if style:
                        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_THICKFRAME)
                        self._thickframe_applied = True
            except Exception:
                pass

    def nativeEvent(self, eventType, message):
        """Handle Windows WM_NCHITTEST for edge/corner resize on frameless window."""
        if sys.platform != "win32":
            return super().nativeEvent(eventType, message)
        try:
            import ctypes
            from ctypes import wintypes

            # message is pointer to MSG struct
            class MSG(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM),
                    ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD),
                    ("pt", wintypes.POINT),
                ]

            msg = MSG.from_address(int(message))
            if msg.message != WM_NCHITTEST:
                return super().nativeEvent(eventType, message)

            # When maximized, let default handling work
            if getattr(self, "isMaximized", lambda: False)():
                return super().nativeEvent(eventType, message)

            # Cursor position (signed 16-bit for multi-monitor)
            x = ctypes.c_short(msg.lParam & 0xFFFF).value
            y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value

            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(msg.hwnd, ctypes.byref(rect))
            b = self._BORDER

            at_left = rect.left <= x < rect.left + b
            at_right = rect.right - b < x <= rect.right
            at_top = rect.top <= y < rect.top + b
            at_bottom = rect.bottom - b < y <= rect.bottom

            if at_top and at_left:
                return True, HTTOPLEFT
            if at_top and at_right:
                return True, HTTOPRIGHT
            if at_bottom and at_left:
                return True, HTBOTTOMLEFT
            if at_bottom and at_right:
                return True, HTBOTTOMRIGHT
            if at_left:
                return True, HTLEFT
            if at_right:
                return True, HTRIGHT
            if at_top:
                return True, HTTOP
            if at_bottom:
                return True, HTBOTTOM

        except Exception:
            pass
        return super().nativeEvent(eventType, message)
