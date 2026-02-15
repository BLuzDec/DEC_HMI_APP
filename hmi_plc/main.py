"""
HMI-PLC sub-application launcher.
Interactive HMI screens for PLC control with Exchange, Recipes, and Requests CSVs.
"""
import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

_hmi_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_hmi_dir)
if _hmi_dir not in sys.path:
    sys.path.insert(0, _hmi_dir)

from PySide6.QtWidgets import QApplication
from main_window import HmiPlcMainWindow

# Export for onboarding dashboard
__all__ = ["HmiPlcMainWindow"]

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HmiPlcMainWindow()
    window.show()
    sys.exit(app.exec())
