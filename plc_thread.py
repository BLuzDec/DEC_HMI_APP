import snap7
from snap7.util import *
import time
import datetime
import logging
import json
import duckdb
import threading

class PLCThread(threading.Thread):
    def __init__(self, ip_address, signal_emitter, status_emitter=None):
        super().__init__()
        self.ip_address = ip_address
        self.signal_emitter = signal_emitter
        self.status_emitter = status_emitter
        self.stop_event = threading.Event()
        self.client = snap7.client.Client()
        self.db_connection = None
        self.name_system = 'Snap7'
        self.read_count = 0
        self.error_count = 0
        self.last_error = None

        with open('snap7_node_ids.json') as f:
            self.config = json.load(f)
        # Support both new generic key and legacy key for backward compatibility
        self.take_specific_nodes = self.config.get('snap7_variables') or self.config.get('Node_id_flexpts_S7_1500_snap7', {})

    def init_duckdb(self):
        self.db_connection = duckdb.connect(database='automation_data.db', read_only=False)
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
            logging.error(f"Failed to read value for {var_name}: {e}")
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
        try:
            self.client.connect(self.ip_address, 0, 1)
            success_msg = f"Successfully connected to PLC at {self.ip_address}"
            logging.info(success_msg)
            self._emit_status("connected", success_msg)
        except Exception as e:
            error_msg = f"Failed to connect to PLC: {e}"
            logging.error(error_msg)
            self._emit_status("error", error_msg)
            return

        while not self.stop_event.is_set():
            try:
                current_values = {}
                for var_name, node_info in self.take_specific_nodes.items():
                    if len(node_info) == 4:
                        db_number, byte_offset, var_type, array_size = node_info
                        value = self.read_signal(db_number, byte_offset, var_type, var_name, array_size)
                    else:
                        db_number, byte_offset, var_type = node_info
                        value = self.read_signal(db_number, byte_offset, var_type, var_name)
                    current_values[var_name] = value
                    self.signal_emitter.emit(var_name, value)
                
                self.read_count += 1
                self.log_data_to_duckdb(current_values)
                
                dose_number = current_values.get('Dose_number')
                if dose_number != last_logged_dose_number:
                    pt_chamber_array = current_values.get('PT_Chamber_Array')
                    if pt_chamber_array:
                        pr_chamber_array = current_values.get('PR_Chamber_Array')
                        self.log_array_data_to_duckdb(dose_number, pt_chamber_array, pr_chamber_array)
                    last_logged_dose_number = dose_number
                
                # Update stats every 100 reads
                if self.read_count % 100 == 0:
                    self._emit_status("stats", "Communication active", {
                        "read_count": self.read_count,
                        "error_count": self.error_count
                    })
                
                time.sleep(0.05)
            except Exception as e:
                self.error_count += 1
                self.last_error = str(e)
                error_msg = f"Communication error: {e}"
                logging.error(error_msg)
                self._emit_status("error", error_msg, {"error_count": self.error_count})
                self.client.disconnect()
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

    def stop(self):
        self.stop_event.set()
        if self.db_connection:
            try:
                self.db_connection.close()
            except:
                pass
