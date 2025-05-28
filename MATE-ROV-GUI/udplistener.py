# save as udp_listener.py
import socket
import json
import datetime

def listen_for_telemetry(port=4891, buffer_size=8192):
    """Listen for UDP telemetry data on the specified port"""
    # Create a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Bind to the port (listen on all available network interfaces)
    sock.bind(('0.0.0.0', port))
    print(f"Listening for UDP telemetry on port {port}...")
    
    try:
        while True:
            # Receive data
            data, addr = sock.recvfrom(buffer_size)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            print(f"\n[{timestamp}] Received {len(data)} bytes from {addr[0]}:{addr[1]}")
            
            # Try to parse as JSON
            try:
                json_data = json.loads(data.decode('utf-8'))
                print(f"JSON Data: {json.dumps(json_data, indent=2)}")
            except json.JSONDecodeError:
                # Not valid JSON, print as string
                print(f"Raw data: {data.decode('utf-8', errors='replace')}")
    except KeyboardInterrupt:
        print("\nStopping listener...")
    finally:
        sock.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Listen for UDP telemetry")
    parser.add_argument("--port", type=int, default=4891, help="Port to listen on")
    args = parser.parse_args()
    
    listen_for_telemetry(args.port)