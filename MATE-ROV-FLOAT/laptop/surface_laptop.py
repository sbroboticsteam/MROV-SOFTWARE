from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import requests
import json
import traceback
from util import write_to_json_file, get_local_ip_address

ESP32_base_url = "http://192.168.0.4:80/"

class helloHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path == '/':
                local_ip = get_local_ip_address()
                if not local_ip:
                    raise ConnectionError("Failed to obtain local IP address.")

                try:
                    response = requests.get(ESP32_base_url + f"start_signal?ip_address={local_ip}", timeout=5)
                    response.raise_for_status()
                except requests.RequestException as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    error_msg = f"Failed to reach ESP32: {str(e)}"
                    self.wfile.write(error_msg.encode('utf-8'))
                    print(error_msg)
                    return

                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(response.text.encode('utf-8'))

            else:
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Not Found")

        except Exception as e:
            self.handle_server_error(e)

    def do_POST(self):
        try:
            if self.path == '/depth':
                content_length = self.headers.get('Content-Length')
                if not content_length:
                    raise ValueError("Missing Content-Length header.")

                post_data = self.rfile.read(int(content_length))
                decoded_data = post_data.decode('utf-8').strip().split(',')

                if len(decoded_data) != 2:
                    raise ValueError("Invalid data format. Expected 'timestamp,depth'.")

                try:
                    timestamp_ms = float(decoded_data[0])
                    depth_value = float(decoded_data[1])
                except ValueError:
                    raise ValueError("Invalid numerical values in data.")

                current_time = round(timestamp_ms * 0.001, 0)
                coordinate = [{"time": current_time, "depth": depth_value}]

                if not write_to_json_file(coordinate):
                    raise IOError("Failed to write to JSON file.")

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"message": "Coordinate received"}).encode('utf-8'))

            else:
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Not Found")

        except Exception as e:
            self.handle_server_error(e)

    def handle_server_error(self, e):
        """Handles internal server errors."""
        print(f"Error: {e}")
        traceback.print_exc()

        self.send_response(500)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Internal Server Error")

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multithreaded HTTP Server."""
    pass

def main():
    PORT = 8000
    try:
        server = ThreadedHTTPServer(('', PORT), helloHandler)
        print(f'Server running on port {PORT}')
        server.serve_forever()
    except Exception as e:
        print(f"Error starting server: {e}")
    except KeyboardInterrupt:
        print("\nShutting down server gracefully.")
        exit(0)

if __name__ == '__main__':
    main()
