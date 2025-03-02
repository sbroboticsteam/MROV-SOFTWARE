# SurfaceLaptop.py

from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import json
import traceback
import os
import requests

# Make sure you update this if your ESP32's base URL changes
# In this example, the ESP32 uses "server.on('/start_signal')",
# so we would call that with e.g. "http://<esp32_ip>/start_signal?ip_address=..."
ESP32_base_url = "http://192.168.0.4:80/"  # Not used if you use send_command.py directly

def write_to_json_file(data_list, filename='coordinates.json'):
    """
    Appends each item in data_list to the JSON array in `filename`.
    Creates the file if it doesn't exist.
    """
    # If file doesn't exist or is empty, start a fresh list
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        with open(filename, 'w') as f:
            json.dump(data_list, f, indent=2)
        return True
    
    # If file exists, load it, append, then rewrite
    try:
        with open(filename, 'r') as f:
            existing_data = json.load(f)
            if not isinstance(existing_data, list):
                existing_data = []
    except:
        existing_data = []
    
    existing_data.extend(data_list)
    
    try:
        with open(filename, 'w') as f:
            json.dump(existing_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Failed to write JSON file: {e}")
        return False

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""
    pass

class MyRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # You can leave this blank or handle test endpoints
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Surface Laptop server is running.")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        if self.path == '/depth':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                raw_post_data = self.rfile.read(content_length)
                data = json.loads(raw_post_data)

                # Expecting a JSON object like:
                # {
                #   "time": <number in ms>,
                #   "depth": <float>,
                #   "pressure": <float>,
                #   "company": <int>
                # }
                # Convert to something we append to coordinates.json
                measurements_to_append = [data]

                # Append to file
                success = write_to_json_file(measurements_to_append, 'coordinates.json')
                if not success:
                    raise IOError("Failed to write to coordinates.json")

                # Send back a JSON response
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                resp = {"message": "DATARECEIVED"}
                self.wfile.write(json.dumps(resp).encode('utf-8'))

            except Exception as e:
                self.send_error_response(e)
    
    def do_GET(self):
        if self.path == '/stop_float':
            try:
                esp32_ip = "192.168.1.78"  # Replace with actual IP of ESP32
                url = f"http://{esp32_ip}/stop_signal"
                # Or if you need to pass anything else, add it as query params

                r = requests.get(url, timeout=5)
                r.raise_for_status()

                # Send a response back to the client indicating success
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                msg = "Stop signal sent to float."
                self.wfile.write(msg.encode('utf-8'))
            except Exception as e:
                self.send_error_response(e)


        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def send_error_response(self, e):
        print(f"Error: {e}")
        traceback.print_exc()
        self.send_response(500)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        resp = {"error": str(e)}
        self.wfile.write(json.dumps(resp).encode('utf-8'))

def main():
    PORT = 8000
    try:
        server = ThreadedHTTPServer(('', PORT), MyRequestHandler)
        print(f'Server running on port {PORT}')
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server gracefully.")
    except Exception as e:
        print(f"Error starting server: {e}")

if __name__ == '__main__':
    main()
