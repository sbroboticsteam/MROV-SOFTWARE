import socket
import sys
import os
import json
import time

# Add the src directory to the Python path

print("Current directory of this script:", os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Now you can import get_controller_input
from controller import get_controller_input

HOST = '192.168.1.237'
PORT = 4891

gen = get_controller_input()
print("get_controller_input is callable:", callable(gen))
while True:
    print("CALLING FROM CLIENT")
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Connect to the Raspberry Pi server
        client_socket.connect((HOST, PORT))
        print(f"Connected to server at {HOST}:{PORT}")
        
        last_data = None

        # Retrieve controller inputs
        for inputs in get_controller_input():
            if inputs != last_data:
                data = json.dumps(inputs)
                # data = data.replace('\r\n', '\n')
                # print(f"Sending: {data}")
                client_socket.sendall(data.encode('utf-8'))
                last_data = inputs 
                time.sleep(0.05)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client_socket.close()
        print("Connection closed.")
        time.sleep(5)
