from main_snap7 import app, plc_communication
import logging
import threading
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

if __name__ == "__main__":
    from waitress import serve
    logging.basicConfig(level=logging.WARNING)
    logging.info("Starting server on http://0.0.0.0:5001")
    
    # Ensure the PLC communication thread is only started once
    if not any(thread.name == "PLCThread" for thread in threading.enumerate()):
        logging.info("Starting PLC communication thread.")
        threading.Thread(target=plc_communication, daemon=True, name="PLCThread").start()
    else:
        logging.info("PLC communication thread already running.")
    
    serve(app, host="0.0.0.0", port=5001)

@app.route('/debug/list_public')
def list_public():
    import os
    try:
        files = os.listdir('public')
        return '<br>'.join(files)
    except Exception as e:
        return f"Error: {e}" 