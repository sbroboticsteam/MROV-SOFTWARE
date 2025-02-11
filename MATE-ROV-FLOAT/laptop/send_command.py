import requests

esp32_ip = "192.168.0.4"
laptop_ip = "192.168.0.148"
url = f"http://{esp32_ip}/start_signal?ip_address={laptop_ip}"

try:
    response = requests.get(url, timeout=10)
    print("Response:", response.text)
except Exception as e:
    print("Error:", e)
