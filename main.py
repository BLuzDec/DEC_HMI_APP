# main.py
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread
from main_window import MainWindow
from plc_simulator import PLCSimulator
from database import DatabaseManager

def main():
    """Main function to run the application."""
    app = QApplication(sys.argv)

    # 1. Initialize Database in a separate thread
    # We create the thread first
    db_thread = QThread()
    db_manager = DatabaseManager('automation_data.db')
    # Move the manager to the thread
    db_manager.moveToThread(db_thread)
    
    # We must start the thread before connecting signals if we want the slot to execute in that thread
    db_thread.start()
    
    # Initialize the table (this happens on the main thread currently, which is fine for init)
    # Ideally, we should do this via a signal/slot too if it takes long, but it's fast.
    db_manager.setup_table()

    # 2. Initialize UI
    window = MainWindow()

    # 3. Initialize PLC Simulator
    simulator = PLCSimulator()

    # 4. Connect signals
    # When the simulator emits new data, update the database (Worker Thread) and the plot (Main Thread)
    simulator.new_data.connect(db_manager.insert_reading)
    simulator.new_data.connect(window.update_plot)

    # 5. Start the simulator thread
    simulator.start()

    # When the window is closed, stop the threads
    app.aboutToQuit.connect(simulator.stop)
    app.aboutToQuit.connect(db_thread.quit)
    app.aboutToQuit.connect(db_thread.wait)

    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
