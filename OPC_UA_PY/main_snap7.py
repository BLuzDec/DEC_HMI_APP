from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import threading
import snap7
from snap7.util import *
import time
import csv
import datetime
import os
import logging
import node_ids

take_specific_nodes = node_ids.Node_id_flexpts_S7_1500_snap7  # node_ids.Node_id_flexpts
name_system = 'FlexPTS'  # 'MicroPTS'

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'public'))
CORS(app)  # Enable CORS to allow communication with Scripts.js

# Global variable to store the latest data
latest_data = {}

def get_size_of_type(var_type):
    """
    Returns the size in bytes for each S7 data type
    """
    sizes = {
        'REAL': 4,    # 32-bit floating point
        'INT': 2,     # 16-bit integer
        'BOOL': 1,    # 1 byte (though we only use 1 bit)
        'DINT': 4,    # 32-bit integer
        'WORD': 2,    # 16-bit unsigned integer
        'DWORD': 4,   # 32-bit unsigned integer
        'BYTE': 1,    # 8-bit unsigned integer
        'STRING': 2   # Minimum size for string (2 bytes for length)
    }
    return sizes.get(var_type, 0)

def connect_to_plc(ip, rack=0, slot=1):
    client = snap7.client.Client()
    try:
        client.connect(ip, rack, slot)
        logging.info("Client successfully connected to PLC.")
        return client
    except Exception as e:
        logging.error("Failed to connect to PLC: %s", e)
        return None

def read_signal(client, db_number, byte_offset, var_type, var_name, array_size=None):
    try:
        # Calculate the size to read
        if array_size:
            # For arrays, read multiple values
            total_size = get_size_of_type(var_type) * array_size
            data = client.db_read(db_number, byte_offset, total_size)
            
            # Convert array data
            if var_type == 'REAL':
                values = []
                for i in range(array_size):
                    value = get_real(data, i * 4)  # 4 bytes per REAL
                    values.append(round(value, 3))
                return values
            else:
                logging.error("Array reading only supported for REAL type")
                return None
        else:
            # Read single value
            data = client.db_read(db_number, byte_offset, get_size_of_type(var_type))
            
            # Convert the data based on the variable type
            if var_type == 'REAL':
                value = get_real(data, 0)
                # Round density values to 4 decimals, others to 3
                if 'Density' in var_name:
                    value = round(value, 4)
                else:
                    value = round(value, 3)
            elif var_type == 'INT':
                value = get_int(data, 0)
            elif var_type == 'BOOL':
                value = get_bool(data, 0, 0)  # Assuming bit 0
            else:
                value = None
                logging.error("Unsupported variable type: %s", var_type)
            
            return value
    except Exception as e:
        logging.error("Failed to read value for %s: %s", var_name, e)
        return None

def log_data(data, variables_name):
    now = datetime.datetime.now()
    current_date = now.date()
    current_time = now.time().replace(microsecond=0)  # without milliseconds
    file_name = f'{current_date}_{name_system}.csv'
    file_exists = os.path.isfile(file_name) and os.path.getsize(file_name) > 0
    with open(file_name, mode='a', newline='') as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow(['Time'] + variables_name)

        writer.writerow([current_time] + data)  # Write data

# COMMENTED OUT: Pressure data logging functionality
# def log_pressure_data(pressure_data):
#     """
#     Log pressure data to a separate CSV file with timestamp
#     """
#     now = datetime.datetime.now()
#     current_date = now.date()
#     current_time = now.time()
#     
#     # Format time with only 3 decimal places for milliseconds
#     time_str = current_time.strftime('%H:%M:%S.%f')[:-3]  # Remove last 3 digits (microseconds)
#     
#     file_name = f'{current_date}_{name_system}_pressure.csv'
#     file_exists = os.path.isfile(file_name) and os.path.getsize(file_name) > 0
#     
#     with open(file_name, mode='a', newline='') as file:
#         writer = csv.writer(file)
# 
#         if not file_exists:
#             writer.writerow(['Time', 'PT_Chamber', 'PR_Chamber', 'PT_Outlet', 'PR_Outlet'])
#     
#         writer.writerow([
#             time_str,
#             pressure_data.get('PT_Chamber', 0),
#             pressure_data.get('PR_Chamber', 0),
#             pressure_data.get('PT_Outlet', 0),
#             pressure_data.get('PR_Outlet', 0)
#         ])

def log_pt_chamber_array_data(dose_number, pt_chamber_array, pr_chamber_array=None):
    """
    Log PT_Chamber_Array data to a separate CSV file when dose_number changes
    Now includes PR_Chamber_Array if provided
    """
    now = datetime.datetime.now()
    current_date = now.date()
    current_time = now.time()
    
    # Format time with only 3 decimal places for milliseconds
    time_str = current_time.strftime('%H:%M:%S.%f')[:-3]  # Remove last 3 digits (microseconds)
    
    file_name = f'{current_date}_{name_system}_pt_chamber_array.csv'
    file_exists = os.path.isfile(file_name) and os.path.getsize(file_name) > 0
    
    with open(file_name, mode='a', newline='') as file:
        writer = csv.writer(file)

        if not file_exists:
            # Create header with PR_Chamber_Array column if it will be included
            if pr_chamber_array is not None:
                header = ['Time', 'Dose_number', 'PT_Chamber_Array', 'PR_Chamber_Array']
            else:
                header = ['Time', 'Dose_number', 'PT_Chamber_Array']
            writer.writerow(header)

        # Create rows, one for each array value (both arrays should have same length)
        array_length = len(pt_chamber_array)
        for i in range(array_length):
            if pr_chamber_array is not None and i < len(pr_chamber_array):
                row = [time_str, dose_number, pt_chamber_array[i], pr_chamber_array[i]]
            else:
                row = [time_str, dose_number, pt_chamber_array[i]]
            writer.writerow(row)

@app.route('/Home.html')
def home():
    return send_from_directory('public', 'Home.html')

@app.route('/Data.html')
def data():
    return send_from_directory('public', 'Data.html')

@app.route('/Dosing.html')
def dosing():
    return send_from_directory('public', 'Dosing.html')

@app.route('/js/<path:path>')
def send_js(path):
    return send_from_directory('public/js', path)

@app.route('/css/<path:path>')
def send_css(path):
    return send_from_directory('public/css', path)

@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory('public/images', filename)

@app.route('/api/data', methods=['GET'])
def get_data():
    return jsonify(latest_data)

@app.route('/api/update', methods=['POST'])
def update_data():
    global latest_data
    data = request.json
    latest_data.update(data)
    return jsonify({"status": "success", "updated_data": latest_data})

@app.route('/api/csv_data', methods=['GET'])
def get_csv_data():
    file_name = f'{datetime.datetime.now().date()}_{name_system}.csv'
    if os.path.isfile(file_name):
        with open(file_name, 'r') as file:
            csv_data = file.read()
        return csv_data
    else:
        return jsonify({"error": "File not found"}), 404

# COMMENTED OUT: Pressure CSV endpoints
# @app.route('/api/pressure_csv', methods=['POST'])
# def log_pressure_csv():
#     """
#     Endpoint to receive and log pressure data to CSV
#     """
#     try:
#         pressure_data = request.json
#         log_pressure_data(pressure_data)
#         return jsonify({"status": "success", "message": "Pressure data logged"})
#     except Exception as e:
#         logging.error("Error logging pressure data: %s", e)
#         return jsonify({"error": str(e)}), 500

# @app.route('/api/pressure_csv_data', methods=['GET'])
# def get_pressure_csv_data():
#     """
#     Endpoint to get pressure CSV data for charts
#     """
#     file_name = f'{datetime.datetime.now().date()}_{name_system}_pressure.csv'
#     if os.path.isfile(file_name):
#         with open(file_name, 'r') as file:
#             csv_data = file.read()
#         return csv_data
#     else:
#         return jsonify({"error": "Pressure file not found"}), 404

@app.route('/api/pt_chamber_array_csv_data', methods=['GET'])
def get_pt_chamber_array_csv_data():
    """
    Endpoint to get PT_Chamber_Array CSV data for charts
    """
    file_name = f'{datetime.datetime.now().date()}_{name_system}_pt_chamber_array.csv'
    if os.path.isfile(file_name):
        with open(file_name, 'r') as file:
            csv_data = file.read()
        return csv_data
    else:
        return jsonify({"error": "PT_Chamber_Array file not found"}), 404

def plc_communication():
    last_logged_dose_number = None
    while True:
        try:
            PLC_IP = "192.168.0.20"
            client = connect_to_plc(PLC_IP)
            
            if client is None:
                raise Exception("Failed to connect to PLC")

            last_successful_communication = time.time()
            last_log_time = time.time()

            while True:
                try:
                    current_values = {}
                    for var_name, node_info in take_specific_nodes.items():
                        # Check if this is an array (has 4 elements in tuple)
                        if len(node_info) == 4:
                            db_number, byte_offset, var_type, array_size = node_info
                            value = read_signal(client, db_number, byte_offset, var_type, var_name, array_size)
                        else:
                            db_number, byte_offset, var_type = node_info
                            value = read_signal(client, db_number, byte_offset, var_type, var_name)
                        
                        current_values[var_name] = value
                    
                    latest_data.update(current_values)  # Update latest data

                    # Log dose-based data if dose_number has changed
                    dose_number = current_values.get('Dose_number')
                    if dose_number != last_logged_dose_number:
                        # Create dose-based data excluding pressure variables and arrays
                        dose_data = {}
                        dose_variables = []
                        for var_name, value in current_values.items():
                            if var_name not in ['FlexPTS_running', 'PT_Chamber', 'PR_Chamber', 'PT_Outlet', 'PR_Outlet', 'PT_Chamber_Array', 'PR_Chamber_Array']:
                                dose_data[var_name] = value
                                dose_variables.append(var_name)
                        
                        log_data(list(dose_data.values()), dose_variables)
                        
                        # Log PT_Chamber_Array data if available
                        pt_chamber_array = current_values.get('PT_Chamber_Array')
                        if pt_chamber_array and isinstance(pt_chamber_array, list):
                            # Get PR_Chamber_Array to include in the same CSV
                            pr_chamber_array = current_values.get('PR_Chamber_Array')
                            log_pt_chamber_array_data(dose_number, pt_chamber_array, pr_chamber_array)
                        
                        last_logged_dose_number = dose_number
                        last_log_time = time.time()

                    # COMMENTED OUT: Pressure data logging functionality
                    # # Log pressure data if FlexPTS_running is true
                    # flexpts_running = current_values.get('FlexPTS_running', False)
                    # # print(f"FlexPTS_running: {flexpts_running}, Type: {type(flexpts_running)}")
                    # 
                    # if flexpts_running:
                    #     pressure_data = {
                    #         'PT_Chamber': current_values.get('PT_Chamber', 0),
                    #         'PR_Chamber': current_values.get('PR_Chamber', 0),
                    #         'PT_Outlet': current_values.get('PT_Outlet', 0),
                    #         'PR_Outlet': current_values.get('PR_Outlet', 0)
                    #     }
                    #     # print(f"Logging pressure data: {pressure_data}")
                    #     log_pressure_data(pressure_data)
                    # else:
                    #     print("FlexPTS_running is False - not logging pressure data")

                    # Debugging: Print the latest data being updated every 10 seconds
                    if not hasattr(plc_communication, "_last_print_time"):
                        plc_communication._last_print_time = 0
                    if time.time() - plc_communication._last_print_time > 10:
                        print("Running at 192.168.0.101:5001/Data.html |", current_values)
                        plc_communication._last_print_time = time.time()

                    # # Debug pressure values specifically
                    # pressure_debug = {
                    #     'FlexPTS_running': current_values.get('FlexPTS_running'),
                    #     'PR_Chamber': current_values.get('PR_Chamber'),
                    #     'PT_Chamber': current_values.get('PT_Chamber'),
                    #     'PT_Outlet': current_values.get('PT_Outlet'),
                    #     'PR_Outlet': current_values.get('PR_Outlet')
                    # }
                    # print(f"Pressure debug values: {pressure_debug}")

                    last_successful_communication = time.time()
                    time.sleep(0.05)  # Delay for 0.5 seconds before reading again

                except Exception as e:
                    logging.error("Error during communication: %s", e)
                    if time.time() - last_successful_communication > 5:
                        logging.error("Communication lost for more than 5 seconds. Restarting...")
                        break

        except Exception as e:
            logging.error("Error in PLC communication: %s", e)

        finally:
            if 'client' in locals() and client is not None:
                client.disconnect()

        logging.info("Restarting PLC communication...")
        time.sleep(5)  # Wait for 5 seconds before restarting

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    if not any(thread.name == "PLCThread" for thread in threading.enumerate()):
        logging.info("Starting PLC communication thread.")
        threading.Thread(target=plc_communication, daemon=True, name="PLCThread").start()
    app.run(host="0.0.0.0", port=5001, debug=False)  # Flask app 