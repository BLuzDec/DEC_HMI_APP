"""
DEC HMI Application - Entry point.
Launches the Onboarding Dashboard from which users can select a sub-application.
"""
import sys
from PySide6.QtWidgets import QApplication
from onboarding_dashboard import OnboardingDashboard

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OnboardingDashboard()
    window.show()
    # Ensure cleanup runs when app quits (e.g. last window closed, or app.quit())
    app.aboutToQuit.connect(window._cleanup_on_close)
    sys.exit(app.exec())
