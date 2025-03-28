#!/usr/bin/env python3
import requests
import socket

def get_laptop_ip():
    """Returns the laptop's IP address on the local network."""
    hostname = socket.gethostname()
    return socket.gethostbyname(hostname)

def send_command(esp32_ip, command, laptop_ip=""):
    """
    Sends the appropriate command to the ESP32.
    
    Parameters:
      esp32_ip: The ESP32 IP address on the network.
      command: One of "s", "vs", "vst", "st", "rs", "a", "d", ".".
      laptop_ip: Required for the start command.
    """
    if command == "s":
        # Start signal: pass the laptop IP so that the ESP32 knows where to send data.
        url = f"http://{esp32_ip}/start_signal?ip_address={laptop_ip}"
    elif command == "vs":
        # Start velocity testing: increase data capture rate.
        url = f"http://{esp32_ip}/start_velocity"
    elif command == "vst":
        # Stop velocity testing: revert data capture rate.
        url = f"http://{esp32_ip}/stop_velocity"
    elif command == "st":
        # Stop float (and pump) command.
        url = f"http://{esp32_ip}/stop_signal"
    elif command == "rs":
        # Start routine: initiate the descent/wait/ascend sequence.
        url = f"http://{esp32_ip}/start_routine"
    elif command == "a":
        # Pump ascend command.
        url = f"http://{esp32_ip}/pump_ascend"
    elif command == "d":
        # Pump descend command.
        url = f"http://{esp32_ip}/pump_descend"
    elif command == ".":
        # Pump stop command.
        url = f"http://{esp32_ip}/pump_stop"
    else:
        print("Invalid command!")
        return

    try:
        response = requests.get(url, timeout=10)
        print("Response:", response.text)
    except Exception as e:
        print("Error sending command:", e)

def main():
    esp32_ip = "192.168.1.78"  # Replace with your ESP32 IP if needed
    laptop_ip = get_laptop_ip()
    print(f"Laptop IP determined as: {laptop_ip}\n")
    print("Available Commands:")
    print("  s   - Start float")
    print("  vs  - Start velocity testing")
    print("  vst - Stop velocity testing")
    print("  st  - Stop float (and pump)")
    print("  rs  - Start routine (descend to >=2.5m, hold >42 sec, then ascend)")
    print("  a   - Float Descend")
    print("  d   - Float Ascend")
    print("  .   - Pump stop")
    print("  q   - Quit")

    while True:
        cmd = input("Enter command: ").strip().lower()
        if cmd == "q":
            print("Exiting.")
            break
        send_command(esp32_ip, cmd, laptop_ip)

if __name__ == '__main__':
    main()
