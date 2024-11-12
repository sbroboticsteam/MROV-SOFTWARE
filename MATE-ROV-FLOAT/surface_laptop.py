from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time
import requests

# Base URL for ESP32 and the server route URL
ESP32_base_url = "http://192.168.1.35/route_name"
server_route_url = "http://192.168.1.44:8000/"

coordinates_set = set()

json_file_path = "coordinates_data.json"

def write_to_json_file(data):
    """Write the coordinates data to a JSON file."""
    with open(json_file_path, 'w') as json_file:
        json.dump(data, json_file, indent=4)
    print(f"Data written to {json_file_path}")

class helloHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        # Handle GET request, including retrieving data from ESP32 if needed
        response = requests.get(ESP32_base_url)  # Get request to the base URL
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write("world".encode())
        if response.status_code == 200:
            print("pass")
        else:
            print("Failed")

    def do_POST(self):
        if self.path == '/depth':
            # Read and process the POST request
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            decoded_data = post_data.decode('utf-8')
            
            print(f"Received data: {decoded_data}")
            try:
                depth_value = float(decoded_data)

                current_time = time.time()

                coordinate = (depth_value, current_time)
                
                coordinates_set.add(coordinate)
                
                print(f"Updated Coordinate Set: {coordinates_set}")

                response_data = {
                    "message": f"Depth received: {depth_value}",
                    "coordinates": [[coord[0], coord[1]] for coord in coordinates_set]
                }

                # Write the data to the JSON file
                write_to_json_file(response_data)

                # Respond to the client
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode('utf-8'))

            except ValueError:
                # Handle invalid depth_value
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid depth value")

        else:
            # If the POST request isn't to `/depth`, send a 404 response
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

def main():
    PORT = 8000
    server = HTTPServer(('', PORT), helloHandler)
    print('Server running on port %s' % PORT)
    server.serve_forever()

if __name__ == '__main__':
    main()
