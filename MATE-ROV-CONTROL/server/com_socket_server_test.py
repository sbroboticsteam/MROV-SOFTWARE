import socket
import json

HOST = '192.168.1.237'
PORT = 4891

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind((HOST, PORT))
server.listen(5)

print(f"Server listening on {HOST}:{PORT}...")

try:
	while True:
		com_socket, addy = server.accept()
		print(f"(Connected to {addy}")
		
		while True:
			data = com_socket.recv(1024)
			if not data:
				break
			motor_values = data.decode('utf-8')
			print(f"These are the motor values:  {motor_values}")
		#message = com_socket.recv(1024)
		#print(message)
		#message1 = message.decode('utf-8')
		#print(message1)
		#if message:
				#controller_inputs = json.loads(message1)
				#print(f"INPUTS from client: {controller_inputs}")
		#print(f"Message from client: {message1}")
		com_socket.send(f"Message recieved".encode('utf-8'))
		
		com_socket.close()
		print(f"Connection with {addy} ended.")
except KeyboardInterrupt:
	print("Server is shutting down...")
finally:
	server.close()
