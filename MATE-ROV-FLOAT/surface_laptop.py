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

def main():
    PORT = 8000
    Server = HTTPServer(('', PORT), helloHandler)
    print('Server running on port %s' % PORT)
    Server.serve_forever()

if __name__ == '__main__':
    main()
