import socket
import json
import os
import traceback

json_file_path = "coordinates_data.json"

def write_to_json_file(new_coordinate):
    """Write the coordinates data to a JSON file with error handling."""
    try:
        if os.path.exists(json_file_path):
            with open(json_file_path, 'r', encoding='utf-8') as json_file:
                try:
                    data = json.load(json_file)
                    if not isinstance(data, dict) or "coordinates" not in data:
                        raise ValueError("Corrupt JSON structure. Resetting file.")
                except json.JSONDecodeError:
                    print("Corrupt JSON file. Resetting data.")
                    data = {"coordinates": []}
        else:
            data = {"coordinates": []}

        data["coordinates"].extend(new_coordinate)

        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(data, json_file, indent=4)

        print(f"Data written to {json_file_path}")
        return True

    except Exception as e:
        print(f"write_to_json_file: Error writing to JSON file: {e}")
        traceback.print_exc()
        return False

def get_local_ip_address():
    """Gets the local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google's public DNS
        IPAddr = s.getsockname()[0]
        s.close()
        return IPAddr
    except Exception as e:
        print(f"get_local_ip_address: Error occurred: {e}")
        return ""
