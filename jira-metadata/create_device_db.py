
import sqlite3
import yaml
import json
import re

DB_FILE = "devices.db"
TABLE_NAME = "devices"
YAML_FILE = "asset_hierarchy.yaml"

def create_database():
    """Creates the SQLite database and the devices table."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f'''
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            device_name TEXT PRIMARY KEY,
            device_id TEXT,
            subvenue_name TEXT,
            subvenue_id TEXT,
            location_name TEXT,
            location_id TEXT,
            venue_name TEXT,
            venue_id TEXT
        )
    ''')
    conn.commit()
    conn.close()

def parse_and_insert_data():
    """Parses the YAML file and inserts the data into the database."""
    with open(YAML_FILE, 'r') as f:
        data = yaml.safe_load(f)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for venue_id, venue_data in data.items():
        venue_name = venue_data.get("details", {}).get("name")
        for subvenue_id, subvenue_data in venue_data.get("subvenue", {}).items():
            subvenue_name = subvenue_data.get("details", {}).get("name")
            for location_id, location_data in subvenue_data.get("location", {}).items():
                location_name = location_data.get("details", {}).get("name")
                for device_id, device_data in location_data.get("device", {}).items():
                    device_name = device_data.get("details", {}).get("name")
                    
                    if device_name:
                        sanitized_device_name = re.sub(r'[^a-zA-Z0-9]', '', device_name)
                        if sanitized_device_name:
                            c.execute(f'''
                                INSERT OR REPLACE INTO {TABLE_NAME} (device_name, device_id, subvenue_name, subvenue_id, location_name, location_id, venue_name, venue_id)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (sanitized_device_name, device_id, subvenue_name, subvenue_id, location_name, location_id, venue_name, venue_id))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_database()
    parse_and_insert_data()
    print(f"Database '{DB_FILE}' created and populated successfully.")

