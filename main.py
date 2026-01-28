from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import threading
import snap7
from snap7.util import *
import time
import datetime
import os
import logging
import json
import duckdb

# Load configuration from JSON file
with open('snap7_node_ids.json') as f:
    config = json.load(f)

take_specific_nodes = config['Node_id_flexpts_S7_1500_snap7']
name_system = 'FlexPTS'

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'public'))
CORS(app)

latest_data = {}
db_connection = None
plc_thread = None
stop_plc_thread = threading.Event()

def init_duckdb():
    global db_connection
    db_connection = duckdb.connect(database='automation_data.db', read_only=False)
    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS exchange_variables (
            timestamp TIMESTAMP,
            name_system VARCHAR,
            variable_name VARCHAR,
            value VARIANT
        )
    ''')
    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS exchange_recipes (
            timestamp TIMESTAMP,
            dose_number INTEGER,
            pt_chamber_array REAL[],
            pr_chamber_array REAL[]
        )
    ''')

def get_size_of_type(var_type):
    sizes = {
        'REAL': 4, 'INT': 2, 'BOOL': 1, 'DINT': 4,
        'WORD': 2, 'DWORD': 4, 'BYTE': 1, 'STRING': 2
    }
    return sizes.get(var_type, 0)

def connect_to_plc(ip, rack=0, slot=1):
    client = snap7.client.Client()
    try:
        client.connect(ip, rack, slot)
        logging.info("Client successfully connected to PLC.")
        return client
    except Exception as e:
        logging.error(f"Failed to connect to PLC: {e}")
        return None

def read_signal(client, db_number, byte_offset, var_type, var_name, array_size=None):
    try:
        if array_size:
            total_size = get_size_of_type(var_type) * array_size
            data = client.db_read(db_number, byte_offset, total_size)
            if var_type == 'REAL':
                return [round(get_real(data, i * 4), 3) for i in range(array_size)]
            logging.error("Array reading only supported for REAL type")
            return None
        else:
            data = client.db_read(db_number, byte_offset, get_size_of_type(var_type))
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

def log_data_to_duckdb(data):
    if db_connection:
        now = datetime.datetime.now()
        for var_name, value in data.items():
            db_connection.execute(
                "INSERT INTO exchange_variables VALUES (?, ?, ?, ?)",
                (now, name_system, var_name, value)
            )

def log_array_data_to_duckdb(dose_number, pt_chamber_array, pr_chamber_array):
    if db_connection:
        now = datetime.datetime.now()
        db_connection.execute(
            "INSERT INTO exchange_recipes VALUES (?, ?, ?, ?)",
            (now, dose_number, pt_chamber_array, pr_chamber_array)
        )

@app.route('/connect', methods=['POST'])
def connect():
    global plc_thread
    ip_address = request.json.get('ip_address', '192.168.0.20')
    if plc_thread is None or not plc_thread.is_alive():
        stop_plc_thread.clear()
        plc_thread = threading.Thread(target=plc_communication, args=(ip_address,), daemon=True)
        plc_thread.start()
        return jsonify({"status": "success", "message": f"Connecting to PLC at {ip_address}"})
    return jsonify({"status": "error", "message": "PLC communication thread already running"})

def plc_communication(ip_address):
    init_duckdb()
    last_logged_dose_number = None
    client = connect_to_plc(ip_address)
    if client is None:
        logging.error("Failed to connect to PLC, thread terminating.")
        return

    while not stop_plc_thread.is_set():
        try:
            last_successful_communication = time.time()
            while not stop_plc_thread.is_set():
                try:
                    current_values = {}
                    for var_name, node_info in take_specific_nodes.items():
                        if len(node_info) == 4:
                            db_number, byte_offset, var_type, array_size = node_info
                            value = read_signal(client, db_number, byte_offset, var_type, var_name, array_size)
                        else:
                            db_number, byte_offset, var_type = node_info
                            value = read_signal(client, db_number, byte_offset, var_type, var_name)
                        current_values[var_name] = value
                    
                    latest_data.update(current_values)
                    log_data_to_duckdb(current_values)
                    
                    dose_number = current_values.get('Dose_number')
                    if dose_number != last_logged_dose_number:
                        pt_chamber_array = current_values.get('PT_Chamber_Array')
                        if pt_chamber_array:
                            pr_chamber_array = current_values.get('PR_Chamber_Array')
                            log_array_data_to_duckdb(dose_number, pt_chamber_array, pr_chamber_array)
                        last_logged_dose_number = dose_number

                    last_successful_communication = time.time()
                    time.sleep(0.05)

                except Exception as e:
                    logging.error(f"Error during communication: {e}")
                    if time.time() - last_successful_communication > 5:
                        logging.error("Communication lost for more than 5 seconds. Reconnecting...")
                        client.disconnect()
                        client = connect_to_plc(ip_address)
                        if client is None:
                            time.sleep(5)
                            continue
        except Exception as e:
            logging.error(f"Error in PLC communication: {e}")
        finally:
            if client:
                client.disconnect()
        logging.info("PLC communication stopped.")
        time.sleep(5)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5001, debug=False)