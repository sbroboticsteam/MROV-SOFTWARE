import asyncio
import websockets

clients = []

async def incomingMessages(websocket, path):
    global clients
    global fastest_time
    message = await websocket.recv()
    if message == "buzz":
        response_time = asyncio.get_event_loop().time()
        clients.append([websocket, response_time])
        if len(clients) == 1:
            await websocket.send("First place!")
            fastest_time = response_time
        else:
            t = round(response_time - fastest_time, 2)
            await websocket.send(f"Repsonse time: {t} sec slower.")

async def input(websocket):
    name = await websocket.recv()
    print(f'Server Received: {name}')
    greeting = f'Hello {name}!'
    
    await websocket.send(greeting)
    print(f'Server Sent: {greeting}')
    
async def main():
    async with websockets.serve(incomingMessages, "localhost", 8765):
        await asyncio.Future() #runs forever
        
if __name__ == "__main__":
    asyncio.run(main())