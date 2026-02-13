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
    sys.exit(app.exec())
