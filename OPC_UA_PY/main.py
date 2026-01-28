from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import threading
from opcua import Client
import time
import csv
import datetime
import os
import logging
import node_ids

take_specific_nodes = node_ids.Node_id_flexpts_S7_1500 #node_ids.Node_id_flexpts
name_system = 'Test_Lab' #'MicroPTS'

app = Flask(__name__, static_folder='public')
CORS(app)  # Enable CORS to allow communication with Scripts.js

# Global variable to store the latest data
latest_data = {}

def connect_to_plc(opc_url):
    client = Client(opc_url)
    try:
        client.connect()
        logging.info("Client successfully connected to OPC UA server.")
    except Exception as e:
        logging.error("Failed to connect to OPC UA server: %s", e)
    return client

def read_signal(client, node_id, var_name):
    try:
        node = client.get_node(node_id)
        value = node.get_value()
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

def plc_communication():
    while True:
        try:
            PLC_IP = "192.168.0.20"
            PORT = "4840"
            opc_url = f"opc.tcp://{PLC_IP}:{PORT}"
            variables = take_specific_nodes.items()
            client = connect_to_plc(opc_url)

            old_values = {var_name: None for var_name in take_specific_nodes.keys()}
            last_successful_communication = time.time()
            last_log_time = time.time()

            while True:
                try:
                    current_values = {}
                    for var_name, node_id in variables:
                        value = read_signal(client, node_id, var_name)
                        current_values[var_name] = value
                    
                    latest_data.update(current_values)  # Update latest data

                    log_data(list(current_values.values()), list(current_values.keys()))
                    last_log_time = time.time()  # Update last log time

                    old_values = current_values.copy()  # Update all old values

                    # Debugging: Print the latest data being updated
                    print("Running at 192.168.0.101:5001/Data.html |", current_values)

                    last_successful_communication = time.time()
                    time.sleep(1)  # Delay for 200ms before reading again

                except Exception as e:
                    logging.error("Error during communication: %s", e)
                    if time.time() - last_successful_communication > 5:
                        logging.error("Communication lost for more than 5 seconds. Restarting...")
                        break

        except Exception as e:
            logging.error("Error in PLC communication: %s", e)

        finally:
            if 'client' in locals():
                client.disconnect()

        logging.info("Restarting PLC communication...")
        time.sleep(5)  # Wait for 5 seconds before restarting

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    if not any(thread.name == "PLCThread" for thread in threading.enumerate()):
        logging.info("Starting PLC communication thread.")
        threading.Thread(target=plc_communication, daemon=True, name="PLCThread").start()  # Removed args parameter
    app.run(debug=True, host="0.0.0.0", port=5001)  # Flask app