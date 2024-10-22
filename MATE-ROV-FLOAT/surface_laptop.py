from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import json

class helloHandler(BaseHTTPRequestHandler):

    # Store (time, depth) data
    data = []

    def do_POST(self):
        if self.path == '/depth':
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body)
            
            if 'time' not in data or 'depth' not in data:
                self.send_response(400)
                return
            
            time = data['time']
            depth = data['depth']
            self.data.append((time, depth))
            self.send_response(200)

def main():
    PORT = 8000
    server = HTTPServer(('', PORT), helloHandler)
    print('Server running on port %s' % PORT)
    server.serve_forever()

if __name__ == '__main__':
    main()
