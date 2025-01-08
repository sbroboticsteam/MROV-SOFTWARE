import socket
import sys
import os

# Add the src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Now you can import get_controller_input
from controller import get_controller_input
HOST = '192.168.0.6'
PORT = 4891

print("CALLING FROM CLIENT")
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    # Connect to the Raspberry Pi server
    client_socket.connect((HOST, PORT))
    print(f"Connected to server at {HOST}:{PORT}")
    
    last_data = None

    # Retrieve controller inputs
    for inputs in get_controller_input():
        if inputs != last_data:
            data = str(inputs) 
            #print(f"Sending: {data}")
            client_socket.sendall(data.encode('utf-8'))  
            last_data = inputs 

except Exception as e:
    print(f"Error: {e}")
finally:
    client_socket.close()
    print("Connection closed.")

# client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# try:
#     # Connect to the server
#     client_socket.connect((HOST, PORT))
#     print(f"Connected to server at {HOST}:{PORT}")

#     # Send a message to the server
#     message = "hello"
#     client_socket.send(message.encode('utf-8'))
#     print(f"Sent message: {message}")

#     # Wait for a response from the server
#     response = client_socket.recv(1024).decode('utf-8')
#     print(f"Received from server: {response}")

# finally:
#     # Close the socket
#     client_socket.close()
#     print("Connection closed.")



# import asyncio
# import websockets

# clients = []

# async def incomingMessages(websocket, path):
#     global clients
#     global fastest_time
#     message = await websocket.recv()
#     if message == "buzz":
#         response_time = asyncio.get_event_loop().time()
#         clients.append([websocket, response_time])
#         if len(clients) == 1:
#             await websocket.send("First place!")
#             fastest_time = response_time
#         else:
#             t = round(response_time - fastest_time, 2)
#             await websocket.send(f"Repsonse time: {t} sec slower.")

# async def input(websocket):
#     name = await websocket.recv()
#     print(f'Server Received: {name}')
#     greeting = f'Hello {name}!'
    
#     await websocket.send(greeting)
#     print(f'Server Sent: {greeting}')
    
# async def main():
#     async with websockets.serve(incomingMessages, "localhost", 8765):
#         await asyncio.Future() #runs forever
        
# if __name__ == "__main__":
#     asyncio.run(main())