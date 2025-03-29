import time
from insta360.rtmp import Client

# Create an RTMP client
client = Client()

# Start capturing video
client.start_capture()
time.sleep(10)

# Stop capturing video
client.stop_capture()
time.sleep(5)

# Close the client
client.close()