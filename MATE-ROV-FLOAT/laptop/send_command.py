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
      command: One of "s", "vs", "vst", "st", "rs", "a", "d", ".", "pid".
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
    elif command == "pid":
        # PID parameter setting
        try:
            kp = input("Enter Kp value (proportional gain): ").strip()
            ki = input("Enter Ki value (integral gain): ").strip()
            kd = input("Enter Kd value (derivative gain): ").strip()
            
            # Build the URL with only the parameters that were provided
            url = f"http://{esp32_ip}/set_pid"
            params = {}
            if kp: params['kp'] = kp
            if ki: params['ki'] = ki
            if kd: params['kd'] = kd
            
            if not params:
                print("No parameters provided. Aborting.")
                return
                
            # Send the request with parameters
            response = requests.get(url, params=params, timeout=10)
            print("Response:", response.text)
            return
            
        except Exception as e:
            print("Error setting PID parameters:", e)
            return
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
    print("  a   - Float Ascend")
    print("  d   - Float Descend")
    print("  .   - Pump stop")
    print("  pid - Set PID parameters")
    print("  q   - Quit")

    while True:
        cmd = input("Enter command: ").strip().lower()
        if cmd == "q":
            print("Exiting.")
            break
        send_command(esp32_ip, cmd, laptop_ip)

if __name__ == '__main__':
    main()