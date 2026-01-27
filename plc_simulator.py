# plc_simulator.py
import time
import random
import csv
import math
import os
from PySide6.QtCore import QThread, Signal

class PLCSimulator(QThread):
    """
    A thread to simulate real-time data from a PLC based on a CSV configuration.
    """
    # Signal signature: variable_name (str), value (float)
    new_data = Signal(str, float)

    def __init__(self, csv_path="exchange_variables.csv", parent=None):
        super().__init__(parent)
        self._is_running = True
        self.csv_path = csv_path
        self.variables = self._load_variables()
        self.sim_state = {var['Variable']: random.uniform(float(var['Min']), float(var['Max'])) for var in self.variables}
        self.tick = 0

    def _load_variables(self):
        variables = []
        if os.path.exists(self.csv_path):
            with open(self.csv_path, mode='r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    variables.append(row)
        return variables

    def run(self):
        """The main loop of the thread."""
        start_time = time.time()
        while self._is_running:
            self.tick += 1
            
            for var in self.variables:
                name = var['Variable']
                min_val = float(var['Min'])
                max_val = float(var['Max'])
                
                if name == "System_Time":
                    # Increment by 1.0 each tick as requested
                    val = self.tick * 1.0
                else:
                    # Create some realistic-looking synthetic data (Sine wave + Noise)
                    # Different phase/frequency for each to make them look distinct
                    noise = (random.random() - 0.5) * (max_val - min_val) * 0.05
                    base_val = (max_val + min_val) / 2
                    amplitude = (max_val - min_val) / 3
                    freq = 0.1 + (hash(name) % 10) / 50.0
                    
                    val = base_val + amplitude * math.sin(self.tick * freq) + noise
                    val = max(min_val, min(val, max_val)) # Clamp
                
                self.new_data.emit(name, val)
            
            # Simulate data acquisition at 2 Hz
            time.sleep(0.5)

    def stop(self):
        """Stops the thread."""
        self._is_running = False
        self.wait()
