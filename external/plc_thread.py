import snap7
from snap7.util import *
import time
import datetime
import logging
import json
import duckdb
import threading
import os

class PLCThread(threading.Thread):
    def __init__(self, ip_address, signal_emitter, status_emitter=None, comm_speed=0.05,
                 recording_reference="time", recording_interval_sec=0.5, recording_trigger_variable=None,
                 db_filename=None):
        super().__init__()
        self.ip_address = ip_address
        self.signal_emitter = signal_emitter
        self.status_emitter = status_emitter
        self.comm_speed = comm_speed  # Communication cycle time in seconds
        self.stop_event = threading.Event()
        self.client = snap7.client.Client()
        self.db_connection = None
        self.name_system = 'FlexPTS'
        self.read_count = 0
        self.error_count = 0
        self.last_error = None
        self._comm_speed_lock = threading.Lock()  # Lock for thread-safe speed updates
        self._write_lock = threading.Lock()  # Lock for thread-safe writes
        # Recording: "time" = log at fixed interval (min 0.1 s); "variable" = log only when trigger variable changes
        self.recording_reference = recording_reference if recording_reference in ("time", "variable") else "time"
        self.recording_interval_sec = max(0.1, float(recording_interval_sec))
        self.recording_trigger_variable = recording_trigger_variable if self.recording_reference == "variable" else None
        self._last_recording_time = None   # for time-based: last time we wrote to DB
        self._last_trigger_value = None   # for variable-based: last value of trigger variable
        
        # Time between last two successfully received packages (ms) - actual cycle time
        self._last_success_read_time = None
        self._last_interval_ms = None
        
        # Track last array read time for 1-second interval
        self.last_array_read_time = {}
        
        # Map array variables to their trigger variables
        self.array_triggers = {
            'arrPT_chamber': 'FlexPTS_running',
            'arrPR_chamber': 'FlexPTS_running',
            'arrPT_Keyence1': 'FlexPTS_running', #FlexPTS_running_Keyence1',
            'arrFT_Keyence1': 'FlexPTS_running', #FlexPTS_running_Keyence1',
            'arrPT_Keyence2': 'FlexPTS_running', #FlexPTS_running_Keyence2',
            'arrFT_Keyence2': 'FlexPTS_running', #FlexPTS_running_Keyence2',
            # Legacy names for backward compatibility
            'PT_Chamber_Array': 'FlexPTS_running',
            'PR_Chamber_Array': 'FlexPTS_running',
        }

        # Get the directory where this file is located
        self.external_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(self.external_dir)
        # Daily DB files: each day gets its own .duckdb file for crash safety and history
        # db_filename: base name without extension, e.g. "Data_09022026". If None, auto-generated.
        self._db_filename_base = db_filename  # None = use default Data_DDMMYYYY
        self._current_db_date = None
        self.db_path = None  # Set in init_duckdb() to today's file
        
        # Load configuration from external folder
        config_path = os.path.join(self.external_dir, 'snap7_node_ids.json')
        with open(config_path) as f:
            self.config = json.load(f)
        
        # Get main node configuration
        node_config = self.config['Node_id_flexpts_S7_1500_snap7']
        
        # Combine regular variables and recipe variables
        self.take_specific_nodes = {}
        
        # Add regular variables (exclude 'recipes' key)
        for key, value in node_config.items():
            if key != 'recipes':
                self.take_specific_nodes[key] = value
        
        # Add recipe variables from 'recipes' section
        if 'recipes' in node_config:
            for key, value in node_config['recipes'].items():
                self.take_specific_nodes[key] = value

    @staticmethod
    def default_db_filename_for_date(dt):
        """Return the default base filename for a date, e.g. 'Data_09022026'."""
        return f"Data_{dt.strftime('%d%m%Y')}"

    def get_db_path_for_date(self, dt):
        """Get the .duckdb file path for a given date, using custom or default filename."""
        if self._db_filename_base:
            fname = self._db_filename_base
        else:
            fname = self.default_db_filename_for_date(dt)
        return os.path.join(self.external_dir, f'{fname}.duckdb')

    def _create_tables(self):
        """Create recording tables if they don't exist."""
        self.db_connection.execute('''
            CREATE TABLE IF NOT EXISTS exchange_variables (
                timestamp TIMESTAMP,
                name_system VARCHAR,
                variable_name VARCHAR,
                value DOUBLE
            )
        ''')
        self.db_connection.execute('''
            CREATE TABLE IF NOT EXISTS exchange_recipes (
                timestamp TIMESTAMP,
                dose_number INTEGER,
                pt_chamber_array REAL[],
                pr_chamber_array REAL[]
            )
        ''')

    def init_duckdb(self):
        """Open today's daily database file (.duckdb). Each day gets its own file.
        If the file already exists (e.g. app restarted same day) it appends to it."""
        today = datetime.date.today()
        self._current_db_date = today
        self.db_path = self.get_db_path_for_date(today)
        self.db_connection = duckdb.connect(database=self.db_path, read_only=False)
        self._create_tables()  # CREATE TABLE IF NOT EXISTS — safe to call on existing file
        logging.info(f"DuckDB opened: {self.db_path}")

    def _check_day_rollover(self):
        """If midnight passed, checkpoint current DB, close it, and open a new daily file."""
        today = datetime.date.today()
        if today != self._current_db_date:
            logging.info(f"Day rollover: closing {self._current_db_date}, opening {today}")
            if self.db_connection:
                try:
                    self.db_connection.execute("CHECKPOINT")
                    self.db_connection.close()
                except Exception as e:
                    logging.warning(f"Error closing DB on day rollover: {e}")
            self._current_db_date = today
            # On rollover, generate new default filename for the new day
            self._db_filename_base = self.default_db_filename_for_date(today)
            self.db_path = self.get_db_path_for_date(today)
            self.db_connection = duckdb.connect(database=self.db_path, read_only=False)
            self._create_tables()
            logging.info(f"DuckDB day rollover complete: {self.db_path}")

    def get_size_of_type(self, var_type):
        sizes = {
            'REAL': 4, 'INT': 2, 'BOOL': 1, 'DINT': 4,
            'WORD': 2, 'DWORD': 4, 'BYTE': 1, 'STRING': 2
        }
        return sizes.get(var_type, 0)

    def read_signal(self, db_number, byte_offset, var_type, var_name, array_size=None):
        try:
            if array_size:
                total_size = self.get_size_of_type(var_type) * array_size
                data = self.client.db_read(db_number, byte_offset, total_size)
                if var_type == 'REAL':
                    return [round(get_real(data, i * 4), 3) for i in range(array_size)]
                logging.error("Array reading only supported for REAL type")
                return None
            else:
                data = self.client.db_read(db_number, byte_offset, self.get_size_of_type(var_type))
                if var_type == 'REAL':
                    value = get_real(data, 0)
                    return round(value, 4 if 'Density' in var_name else 3)
                elif var_type == 'INT':
                    return get_int(data, 0)
                elif var_type == 'BOOL':
                    return get_bool(data, 0, 0)
                else:
                    logging.error(f"Unsupported variable type: {var_type}")
                    return None
        except Exception as e:
            # Only log error if it's not an address out of range error (which means variable doesn't exist)
            error_str = str(e)
            if 'Address out of range' not in error_str and 'out of range' not in error_str.lower():
                logging.error(f"Failed to read value for {var_name}: {e}")
            # Return None for any read error - this will be filtered out upstream
            return None

    def log_data_to_duckdb(self, data):
        if self.db_connection:
            now = datetime.datetime.now()
            for var_name, value in data.items():
                # Convert value to double (skip arrays and None values)
                if value is None:
                    continue
                if isinstance(value, (list, tuple)):
                    continue  # Arrays are logged separately
                try:
                    numeric_value = float(value) if not isinstance(value, (int, float)) else value
                    self.db_connection.execute(
                        "INSERT INTO exchange_variables VALUES (?, ?, ?, ?)",
                        (now, self.name_system, var_name, numeric_value)
                    )
                except (ValueError, TypeError):
                    # Skip non-numeric values
                    continue

    def log_array_data_to_duckdb(self, dose_number, pt_chamber_array, pr_chamber_array):
        if self.db_connection:
            now = datetime.datetime.now()
            self.db_connection.execute(
                "INSERT INTO exchange_recipes VALUES (?, ?, ?, ?)",
                (now, dose_number, pt_chamber_array, pr_chamber_array)
            )

    def _emit_status(self, status_type, message, details=None):
        """Emit status update to UI"""
        if self.status_emitter:
            self.status_emitter.emit(status_type, message, details or {})

    def run(self):
        self._emit_status("info", "Initializing database...")
        try:
            self.init_duckdb()
            self._emit_status("info", "Database initialized successfully")
        except Exception as e:
            error_msg = f"Database initialization failed: {e}"
            logging.error(error_msg)
            self._emit_status("error", error_msg)
            return
        
        self._emit_status("info", f"Connecting to PLC at {self.ip_address}...")
        last_logged_dose_number = None
        # Track trigger variable states (persists across loop iterations)
        trigger_states = {}
        try:
            self.client.connect(self.ip_address, 0, 1)
            success_msg = f"Successfully connected to PLC at {self.ip_address}"
            logging.info(success_msg)
            self._emit_status("connected", success_msg)
        except Exception as e:
            error_msg = f"Failed to connect to PLC: {e}"
            logging.error(error_msg)
            self._emit_status("error", error_msg)
            # Emit disconnected status so UI can re-enable inputs
            self._emit_status("disconnected", "Connection failed")
            return

        while not self.stop_event.is_set():
            try:
                current_values = {}
                # Separate arrays from scalars to read arrays with delay
                array_vars = []
                scalar_vars = []
                
                for var_name, node_info in self.take_specific_nodes.items():
                    if len(node_info) == 4:
                        array_vars.append((var_name, node_info))
                    else:
                        scalar_vars.append((var_name, node_info))
                
                # Read scalar variables first (faster)
                for var_name, node_info in scalar_vars:
                    try:
                        db_number, byte_offset, var_type = node_info
                        value = self.read_signal(db_number, byte_offset, var_type, var_name)
                        
                        if value is not None:
                            try:
                                float(value)
                                current_values[var_name] = value
                                self.signal_emitter.emit(var_name, value)
                                
                                # Store trigger variable state for array reading (all arrays use FlexPTS_running)
                                if var_name == 'FlexPTS_running':
                                    trigger_states[var_name] = bool(value)
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logging.debug(f"Skipping scalar variable {var_name} due to error: {e}")
                        continue
                
                # Read array variables only when trigger is TRUE and 1 second has passed
                current_time = time.time()
                for var_name, node_info in array_vars:
                    # Get the trigger variable for this array
                    trigger_var = self.array_triggers.get(var_name)
                    if not trigger_var:
                        # No trigger defined, skip this array
                        continue
                    
                    # Check if trigger is TRUE
                    trigger_state = trigger_states.get(trigger_var, False)
                    if not trigger_state:
                        # Trigger is FALSE - don't read arrays
                        continue
                    
                    # Check if 1 second has passed since last read for this array
                    last_read = self.last_array_read_time.get(var_name, 0)
                    if current_time - last_read < 1.0:
                        # Less than 1 second since last read - skip this cycle
                        continue
                    
                    # Trigger is TRUE and 1 second has passed - read the array
                    try:
                        db_number, byte_offset, var_type, array_size = node_info
                        value = self.read_signal(db_number, byte_offset, var_type, var_name, array_size)
                        
                        # Update last read time
                        self.last_array_read_time[var_name] = current_time
                        
                        if value is not None and isinstance(value, list) and len(value) > 0:
                            # Successfully received array data - emit full array for plotting
                            current_values[var_name] = value
                            # For arrays, emit the full array so all values can be plotted at once
                            self.signal_emitter.emit(var_name, value)
                        else:
                            # Array read returned None or empty - don't emit, preserve last known value
                            logging.debug(f"Array {var_name} returned None/empty, preserving last known value")
                    except Exception as e:
                        # Log error but continue - preserve last known value
                        error_str = str(e)
                        if 'Job pending' in error_str or 'CLI' in error_str:
                            logging.debug(f"PLC busy for array {var_name}, preserving last known value")
                        else:
                            logging.debug(f"Array {var_name} read failed: {e}")
                        continue
                
                self.read_count += 1
                # Measure actual time between this and previous received package
                now = time.time()
                if self._last_success_read_time is not None:
                    self._last_interval_ms = (now - self._last_success_read_time) * 1000
                self._last_success_read_time = now
                
                # Decide whether to record this cycle: time-based (interval) or variable-based (on change)
                should_log = False
                if self.recording_reference == "time":
                    if self._last_recording_time is None or (now - self._last_recording_time) >= self.recording_interval_sec:
                        should_log = True
                        self._last_recording_time = now
                else:
                    # variable: record when trigger variable value changes (or first time we see it)
                    trigger_val = current_values.get(self.recording_trigger_variable) if self.recording_trigger_variable else None
                    if trigger_val is not None:
                        if self._last_trigger_value is None or trigger_val != self._last_trigger_value:
                            should_log = True
                        self._last_trigger_value = trigger_val
                    if should_log:
                        self._last_recording_time = now  # for purge / stats
                
                if should_log:
                    self.log_data_to_duckdb(current_values)
                    dose_number = current_values.get('Dose_number')
                    pt_chamber_array = current_values.get('arrPT_chamber') or current_values.get('PT_Chamber_Array')
                    if pt_chamber_array and dose_number is not None:
                        pr_chamber_array = current_values.get('arrPR_chamber') or current_values.get('PR_Chamber_Array')
                        self.log_array_data_to_duckdb(dose_number, pt_chamber_array, pr_chamber_array)
                
                # For time-based we also log array when dose_number changes (even if not this interval)
                if self.recording_reference == "time":
                    dose_number = current_values.get('Dose_number')
                    if dose_number != last_logged_dose_number:
                        pt_chamber_array = current_values.get('arrPT_chamber') or current_values.get('PT_Chamber_Array')
                        if pt_chamber_array:
                            pr_chamber_array = current_values.get('arrPR_chamber') or current_values.get('PR_Chamber_Array')
                            self.log_array_data_to_duckdb(dose_number, pt_chamber_array, pr_chamber_array)
                        last_logged_dose_number = dose_number
                
                # Day rollover check (every ~500 cycles): if midnight passed, open new daily file
                if self.read_count % 500 == 0:
                    self._check_day_rollover()
                
                # Periodic CHECKPOINT for crash safety (every ~1000 cycles ≈ 50s at 50ms)
                if self.read_count % 1000 == 0 and self.db_connection:
                    try:
                        self.db_connection.execute("CHECKPOINT")
                    except Exception as e:
                        logging.debug(f"Checkpoint skipped: {e}")
                
                # Update stats every 100 reads
                if self.read_count % 100 == 0:
                    details = {
                        "read_count": self.read_count,
                        "error_count": self.error_count
                    }
                    if self._last_interval_ms is not None:
                        details["last_interval_ms"] = self._last_interval_ms
                    with self._comm_speed_lock:
                        details["requested_interval_ms"] = self.comm_speed * 1000
                    self._emit_status("stats", "Communication active", details)
                
                # Get current speed value (thread-safe)
                with self._comm_speed_lock:
                    current_speed = self.comm_speed
                time.sleep(current_speed)
            except Exception as e:
                self.error_count += 1
                self.last_error = str(e)
                error_msg = f"Communication error: {e}"
                logging.error(error_msg)
                self._emit_status("error", error_msg, {"error_count": self.error_count})
                
                # Disconnect and attempt reconnection
                try:
                    self.client.disconnect()
                except:
                    pass  # Ignore disconnect errors
                
                self._emit_status("info", "Attempting to reconnect in 5 seconds...")
                time.sleep(5)
                
                try:
                    self.client.connect(self.ip_address, 0, 1)
                    self._emit_status("connected", f"Reconnected to PLC at {self.ip_address}")
                except Exception as e:
                    reconnect_error = f"Reconnection failed: {e}"
                    logging.error(reconnect_error)
                    self._emit_status("error", reconnect_error)
                    time.sleep(5)
        
        self.client.disconnect()
        stop_msg = "PLC communication stopped."
        logging.info(stop_msg)
        self._emit_status("disconnected", stop_msg)

    def update_speed(self, new_speed):
        """Update communication speed dynamically (thread-safe)"""
        if new_speed > 0:
            with self._comm_speed_lock:
                self.comm_speed = new_speed
    
    def write_bool(self, var_name, value):
        """Write a boolean value to the PLC"""
        with self._write_lock:
            try:
                if var_name not in self.take_specific_nodes:
                    logging.error(f"Variable {var_name} not found in configuration")
                    return False
                
                node_info = self.take_specific_nodes[var_name]
                if len(node_info) == 3:
                    db_number, byte_offset, var_type = node_info
                    if var_type != "BOOL":
                        logging.error(f"Variable {var_name} is not a BOOL type")
                        return False
                    
                    # Read current byte
                    data = bytearray(self.client.db_read(db_number, byte_offset, 1))
                    # Set bit 0 to the desired value
                    set_bool(data, 0, 0, value)
                    # Write back
                    self.client.db_write(db_number, byte_offset, data)
                    logging.info(f"Wrote {var_name} = {value}")
                    return True
                else:
                    logging.error(f"Invalid node info for {var_name}")
                    return False
            except Exception as e:
                logging.error(f"Failed to write {var_name}: {e}")
                return False

    def trigger_bool_pulse(self, var_name, pulse_duration=0.5):
        """Trigger a boolean pulse: set to True, wait, then set to False"""
        def pulse_thread():
            try:
                # Set to True
                if self.write_bool(var_name, True):
                    # Wait for pulse duration
                    time.sleep(pulse_duration)
                    # Set back to False
                    self.write_bool(var_name, False)
                    logging.info(f"Completed pulse for {var_name}")
            except Exception as e:
                logging.error(f"Error in pulse thread for {var_name}: {e}")
        
        # Run pulse in a separate thread to avoid blocking
        pulse_thread_obj = threading.Thread(target=pulse_thread, daemon=True)
        pulse_thread_obj.start()
        return pulse_thread_obj

    def stop(self):
        self.stop_event.set()
        if self.db_connection:
            try:
                self.db_connection.execute("CHECKPOINT")
                self.db_connection.close()
            except:
                pass
