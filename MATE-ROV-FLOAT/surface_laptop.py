from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import sysconfig

# Printing sysconfig paths for debugging
print(sysconfig.get_paths())

ESP32_base_url = "http://192.168.1.35:port/route_name"
server_route_url = "http://192.168.1.44:8000/"

class helloHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        #response = requests.get(ESP32_base_url)  # Get request to the base URL
        self.send_response(200)
        self.send_header('content-type', 'text/html')
        self.end_headers()
        self.wfile.write("world".encode())
        if response.status_code == 200:
            print("pass")
        else:
            print("Failed")

    def do_POST(self):
        if self.path == '/depth':
            content_length = int(self.headers['Content-Length'])  # Get the size of data
            print(content_length)
            post_data = self.rfile.read(content_length)  # Read the data
            decoded_data = post_data.decode('utf-8')
            #data = json.loads(post_data)  # Decode JSON data
            print(decoded_data)
            # Here you can process `data` as needed; for example:
            depth_value = post_data
            
            # Respond to the client
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {"message": f"Depth received: {depth_value}"}
            self.wfile.write(json.dumps(response).encode())

        else:
            # If the POST request isn't to `/depth`, send a 404 response
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

def main():
    PORT = 8000
    Server = HTTPServer(('', PORT), helloHandler)
    print('Server running on port %s' % PORT)
    Server.serve_forever()

if __name__ == '__main__':
    main()
