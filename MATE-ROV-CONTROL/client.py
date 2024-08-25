import asyncio
import websockets
import keyboard


async def start_client():
    async with websockets.connect("ws://localhost:8765") as websocket:
        done = False
        while not done:
            if keyboard.is_pressed("space"):
                await websocket.send("buzz")
                message = await websocket.recv()
                print(message)
                done = True

async def hello():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        name = input("What's your name? ")
        
        await websocket.send(name)
        print(f'Client sent: {name}')
        
        greeting = await websocket.recv()
        print(f'Client recieved: {greeting}')
        
if __name__ == "__main__":
    asyncio.run(start_client())