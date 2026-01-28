# database.py
from PySide6.QtCore import QObject, Slot
import duckdb
import datetime
import os

class DatabaseManager(QObject):
    """A class to manage interactions with the DuckDB database."""
    def __init__(self, db_file=None):
        super().__init__()
        # Get the directory where this file is located
        self.external_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Default database path in external folder
        if db_file is None:
            db_file = os.path.join(self.external_dir, 'automation_data.db')
        
        self.db_file = db_file
        self.con = duckdb.connect(database=self.db_file, read_only=False)

    def setup_table(self):
        """Creates the 'readings' table if it doesn't exist."""
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                timestamp DATETIME,
                variable_name VARCHAR,
                value DOUBLE
            )
        """)

    @Slot(str, float)
    def insert_reading(self, variable_name, value):
        """Inserts a single reading into the database."""
        timestamp = datetime.datetime.now()
        try:
            self.con.execute(
                "INSERT INTO readings VALUES (?, ?, ?)",
                (timestamp, variable_name, value)
            )
            # print(f"Inserted: {timestamp}, {variable_name}, {value}") # Removed to prevent UI lag
        except Exception as e:
            print(f"DB Error: {e}")

    def export_to_csv(self, variable_name, output_path):
        """Exports data for a specific variable to a CSV file."""
        query = f"COPY (SELECT * FROM readings WHERE variable_name = '{variable_name}') TO '{output_path}' WITH (HEADER 1, DELIMITER ',');"
        self.con.execute(query)
        print(f"Data for '{variable_name}' exported to '{output_path}'")

    def __del__(self):
        """Ensure the database connection is closed when the object is destroyed."""
        try:
            self.con.close()
        except:
            pass
