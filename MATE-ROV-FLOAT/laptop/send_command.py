import requests
import socket

# Get laptop ip address on the network. 
hostname = socket.gethostname()
laptop_ip = socket.gethostbyname(hostname)

esp32_ip = "192.168.0.4"  # Replace with actual IP of your ESP32 on the network
url = f"http://{esp32_ip}/start_signal?ip_address={laptop_ip}"

try:
    response = requests.get(url, timeout=10)
    print("Response:", response.text)
except Exception as e:
    print("Error:", e)
