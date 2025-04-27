# import socket
# import json

# HOST = '10.0.0.3'
# PORT = 4891

# server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# server.bind((HOST, PORT))
# server.listen(5)

# print(f"Server listening on {HOST}:{PORT}...")

# try:
# 	while True:
# 		com_socket, addy = server.accept()
# 		print(f"(Connected to {addy}")
		
# 		while True:
# 			data = com_socket.recv(1024)
# 			if not data:
# 				break
# 			motor_values = data.decode('utf-8')
# 			print(f"These are the motor values:  {motor_values}")
# 		#message = com_socket.recv(1024)
# 		#print(message)
# 		#message1 = message.decode('utf-8')
# 		#print(message1)
# 		#if message:
# 				#controller_inputs = json.loads(message1)
# 				#print(f"INPUTS from client: {controller_inputs}")
# 		#print(f"Message from client: {message1}")
# 		com_socket.send(f"Message recieved".encode('utf-8'))
		
# 		com_socket.close()
# 		print(f"Connection with {addy} ended.")
# except KeyboardInterrupt:
# 	print("Server is shutting down...")
# finally:
# 	server.close()


import socket
import json

HOST = '192.168.1.237'
PORT = 4891

# Change to UDP socket
server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Optional but can be helpful for quick restarts
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind((HOST, PORT))

print(f"UDP Server listening on {HOST}:{PORT}...")

try:
    while True:
        # For UDP, recvfrom() returns both data and sender address in one call
        data, addy = server.recvfrom(1024)
        if data:
            motor_values = data.decode('utf-8')
            print(f"Received from {addy}:")
            print(f"Data: {motor_values}")
            
            try:
                # Try to parse as JSON if it's in that format
                json_data = json.loads(motor_values)
                print(f"Parsed JSON: {json_data}")
            except json.JSONDecodeError:
                # If not valid JSON, just show the raw data
                pass
                
            # To reply to the client (optional):
            server.sendto("Message received".encode('utf-8'), addy)
            
except KeyboardInterrupt:
    print("Server is shutting down...")
finally:
    server.close()