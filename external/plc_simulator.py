# plc_simulator.py
import time
import random
import csv
import math
import os
from PySide6.QtCore import QThread, Signal

class PLCSimulator(QThread):
    """
    A thread to simulate real-time data from a PLC, including dynamic recipe parameters.
    """
    new_data = Signal(str, object)

    def __init__(self, csv_path=None, parent=None):
        super().__init__(parent)
        self._is_running = True
        
        # Get the directory where this file is located
        self.external_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Default CSV path in external folder — prefer DB-named CSVs
        if csv_path is None:
            try:
                from variable_loader import discover_csv_files
                _disc_ex, _ = discover_csv_files(self.external_dir)
                csv_path = _disc_ex or os.path.join(self.external_dir, 'exchange_variables.csv')
            except Exception:
                csv_path = os.path.join(self.external_dir, 'exchange_variables.csv')
        self.csv_path = csv_path
        
        self.variables = self._load_variables()
        self.variable_details = {var['Variable']: var for var in self.variables}
        self.recipe_params = []
        recipe_vars = self._load_recipe_variables()
        for var in recipe_vars:
            vname = var.get('Variable', '').strip()
            if vname and vname not in self.variable_details:
                self.variable_details[vname] = var
                self.recipe_params.append(vname)
        if not self.recipe_params:
            self.recipe_params = [
                'Recipe_ID', 'Recipe_Step_Time', 'Recipe_Temperature_Set',
                'Recipe_Pressure_Set', 'Recipe_Flow_Rate', 'Recipe_Mixer_Speed',
                'Recipe_Conveyor_Speed', 'Recipe_Coating_Thickness',
                'Recipe_Curing_Time', 'Recipe_Batch_Size'
            ]
            for vname in self.recipe_params:
                if vname not in self.variable_details:
                    self.variable_details[vname] = {'Variable': vname, 'Min': '0', 'Max': '10'}

        # Initialize sim_state for exchange + recipe variables (so tooltip gets recipe values)
        self.sim_state = {}
        for var in self.variables:
            try:
                self.sim_state[var['Variable']] = random.uniform(float(var['Min']), float(var['Max']))
            except (ValueError, KeyError) as e:
                print(f"Warning: Could not initialize variable '{var.get('Variable', 'N/A')}'. Check CSV format. Error: {e}")
                self.sim_state[var.get('Variable', 'N/A')] = 0
        for vname in self.recipe_params:
            if vname not in self.sim_state:
                details = self.variable_details.get(vname, {})
                try:
                    mn = float(details.get('Min', 0))
                    mx = float(details.get('Max', 10))
                    self.sim_state[vname] = random.uniform(mn, mx)
                except (ValueError, TypeError):
                    self.sim_state[vname] = 0.0

        self.tick = 0

    @staticmethod
    def _detect_delimiter(path):
        """Auto-detect CSV delimiter (comma or semicolon) from the first line."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline()
                if ";" in first_line and "," not in first_line:
                    return ";"
                if first_line.count(";") > first_line.count(","):
                    return ";"
        except Exception:
            pass
        return ","

    def _load_variables(self):
        variables = []
        if os.path.exists(self.csv_path):
            delimiter = self._detect_delimiter(self.csv_path)
            with open(self.csv_path, mode='r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile, delimiter=delimiter)
                variables = list(reader)
        # Fallback if CSV is locked or empty
        if not variables:
            print("Warning: exchange_variables.csv could not be read or is empty. Using fallback variables.")
            # This is the list of variables we expect, including the new recipe ones.
            # This makes the simulator runnable even if the CSV is locked.
            return [
                {'Variable': 'System_Time', 'Min': '0', 'Max': '100000'},
                {'Variable': 'Pressure_In', 'Min': '0', 'Max': '10'},
                {'Variable': 'Pressure_Out', 'Min': '0', 'Max': '10'},
                {'Variable': 'Flow_Rate', 'Min': '0', 'Max': '500'},
                {'Variable': 'Temp_Reactor', 'Min': '20', 'Max': '150'},
                {'Variable': 'Level_Tank', 'Min': '0', 'Max': '100'},
                # Add all other variables you expect to be in the CSV...
                {'Variable': 'Recipe_ID', 'Min': '1', 'Max': '10'},
                {'Variable': 'Recipe_Step_Time', 'Min': '10', 'Max': '100'},
                {'Variable': 'Recipe_Temperature_Set', 'Min': '50', 'Max': '250'},
                {'Variable': 'Recipe_Pressure_Set', 'Min': '1', 'Max': '10'},
                {'Variable': 'Recipe_Flow_Rate', 'Min': '100', 'Max': '1000'},
                {'Variable': 'Recipe_Mixer_Speed', 'Min': '500', 'Max': '2000'},
                {'Variable': 'Recipe_Conveyor_Speed', 'Min': '0.1', 'Max': '2.0'},
                {'Variable': 'Recipe_Coating_Thickness', 'Min': '0.01', 'Max': '0.1'},
                {'Variable': 'Recipe_Curing_Time', 'Min': '60', 'Max': '600'},
                {'Variable': 'Recipe_Batch_Size', 'Min': '1', 'Max': '100'}
            ]
        return variables

    def _load_recipe_variables(self):
        """Load recipe variables CSV so simulator can emit them for tooltip (same format as exchange)."""
        try:
            from variable_loader import discover_csv_files
            _, _disc_rec = discover_csv_files(self.external_dir)
            recipe_path = _disc_rec or os.path.join(self.external_dir, 'recipe_variables.csv')
        except Exception:
            recipe_path = os.path.join(self.external_dir, 'recipe_variables.csv')
        variables = []
        if os.path.exists(recipe_path):
            try:
                delimiter = self._detect_delimiter(recipe_path)
                with open(recipe_path, mode='r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f, delimiter=delimiter)
                    variables = [row for row in reader if (row.get('Variable') or '').strip()]
            except Exception as e:
                print(f"Warning: Could not read recipe_variables.csv: {e}")
        return variables

    def run(self):
        """The main loop of the thread."""
        while self._is_running:
            self.tick += 1

            # --- Change a recipe parameter every 10 seconds ---
            if self.tick % 20 == 0: # 20 ticks * 0.5s/tick = 10s
                param_to_change = random.choice(self.recipe_params)
                
                if param_to_change in self.variable_details:
                    details = self.variable_details[param_to_change]
                    try:
                        min_val = float(details['Min'])
                        max_val = float(details['Max'])
                        
                        # Generate a new value. If it's an ID, make it an integer.
                        if param_to_change == 'Recipe_ID':
                            new_val = random.randint(int(min_val), int(max_val))
                        else:
                            new_val = random.uniform(min_val, max_val)
                            
                        self.sim_state[param_to_change] = new_val
                        self.new_data.emit(param_to_change, new_val)

                    except (ValueError, KeyError) as e:
                        print(f"Error processing recipe param '{param_to_change}': {e}")

            # --- Emit standard variable data ---
            # We emit these every tick, including the (mostly static) recipe values
            for var_name in self.sim_state.keys():
                # Skip the recipe param we just updated to avoid emitting twice
                if self.tick % 20 == 0 and var_name in self.recipe_params:
                    continue

                details = self.variable_details.get(var_name)
                if not details: continue
                
                val = self.sim_state[var_name]
                
                # Update logic for non-recipe variables
                if var_name not in self.recipe_params:
                    min_val = float(details['Min'])
                    max_val = float(details['Max'])

                    if var_name == "System_Time":
                        val = self.tick * 1.0
                    else:
                        # Synthetic data wave
                        noise = (random.random() - 0.5) * (max_val - min_val) * 0.05
                        base_val = (max_val + min_val) / 2
                        amplitude = (max_val - min_val) / 3
                        freq = 0.1 + (hash(var_name) % 10) / 50.0
                        val = base_val + amplitude * math.sin(self.tick * freq) + noise
                        val = max(min_val, min(val, max_val))
                    
                    self.sim_state[var_name] = val
                
                self.new_data.emit(var_name, val)
            
            time.sleep(0.5)

    def stop(self):
        """Stops the thread."""
        self._is_running = False
        self.wait()
