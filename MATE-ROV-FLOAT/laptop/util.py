import socket
import json

json_file_path = "coordinates_data.json"

def write_to_json_file(new_coordinate):
    """Write the coordinates data to a JSON file."""
    try:
        with open(json_file_path, 'r') as json_file:
            try:
                data = json.load(json_file)
            except json.JSONDecodeError:
                data = {"coordinates": []}
    except FileNotFoundError:
        data = {"coordinates": []}

    data["coordinates"].extend(new_coordinate)
    with open(json_file_path, 'w') as json_file:
        json.dump(data, json_file, indent=4)

    print(f"Data written to {json_file_path}")

def get_local_ip_address():
    try:
        # Attempt to connect to a public IP address to find the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google's public DNS
        IPAddr = s.getsockname()[0]
        s.close()
        return IPAddr
    except Exception as e:
        print(f"get_local_ip_address: An error occurred: {e}")
        return ""