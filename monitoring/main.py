"""
Monitoring sub-application launcher.
Runs the main monitoring window with PLC communication, analytics, and data recording.
"""
import sys
import os

# Ensure project root is on path so monitoring package imports work
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

# Change to monitoring dir so that "from external" resolves to monitoring/external
_monitoring_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_monitoring_dir)
if _monitoring_dir not in sys.path:
    sys.path.insert(0, _monitoring_dir)

from PySide6.QtWidgets import QApplication
from main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
