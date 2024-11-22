from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import requests
import json
from util import write_to_json_file, get_local_ip_address

ESP32_base_url = "http://192.168.1.91:80/"

class helloHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path == '/':
                # Send GET start_signal request to ESP32
                with requests.get(ESP32_base_url + "start_signal?ip_address=" + get_local_ip_address()) as response: # Get request to the base URL
                    print(response.text)
                    # Respond with status 200 if ESP32 successfully start
                    if response.status_code == 200:
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers() 
                        self.wfile.write(response.text.encode('utf-8'))           
                    else:
                        self.send_response(response.status_code)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(f"Failed with status code: {response.status_code} - {response.text}".encode('utf-8'))           
            else:
                # If the GET request isn't to `/`, send a 404 response
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Not Found")
        except Exception as e:     
            print(f"GET Route: An error occurred: {e}")

    def do_POST(self):
        if self.path == '/depth':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            decoded_data = post_data.decode('utf-8').split(',')
            # Record the (time, depth) coordinate in json_file_path
            try:
                depth_value = float(decoded_data[1])
                current_time = round(float(decoded_data[0])*0.001, 0)
                coordinate = [{"time": current_time, "depth": depth_value}]
                write_to_json_file(coordinate)

                # Respond to the client
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps("Coordinate received").encode('utf-8'))
            except ValueError:
                # Handle invalid depth_value
                self.send_response(400)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Failed to store the coordinate")
        else:
            # If the POST request isn't to `/depth`, send a 404 response
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Not Found") 

# Define the threaded HTTP server class
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass

def main():
    PORT = 8000
    # Directly use ThreadingMixIn with HTTPServer without subclassing
    server = ThreadedHTTPServer(('', PORT), helloHandler)  
    print('Server running on port %s' % PORT)
    server.serve_forever()

if __name__ == '__main__':
    main()