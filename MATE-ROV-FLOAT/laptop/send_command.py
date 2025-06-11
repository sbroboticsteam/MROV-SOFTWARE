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
    elif command == "vel":
        # Velocity limits setting
        try:
            descent = input("Enter max descent velocity (m/s, positive value): ").strip()
            ascent = input("Enter max ascent velocity (m/s, positive value): ").strip()
            
            # Build the URL with only the parameters that were provided
            url = f"http://{esp32_ip}/set_velocity"
            params = {}
            if descent: params['descent'] = descent
            if ascent: params['ascent'] = ascent
            
            if not params:
                print("No parameters provided. Aborting.")
                return
                
            # Send the request with parameters
            response = requests.get(url, params=params, timeout=10)
            print("Response:", response.text)
            return
            
        except Exception as e:
            print("Error setting velocity limits:", e)
            return
    # Add this to the send_command function in send_command.py
    elif command == "wait":
        try:
            seconds = input("Enter wait time in seconds: ").strip()
            if not seconds or not seconds.isdigit() or int(seconds) <= 0:
                print("Invalid input. Please enter a positive number.")
                return
                
            url = f"http://{esp32_ip}/set_wait_time?seconds={seconds}"
            response = requests.get(url, timeout=10)
            print("Response:", response.text)
            return
            
        except Exception as e:
            print("Error setting wait time:", e)
            return 
    # Add to the send_command function in send_command.py
    elif command == "pid_toggle":
        url = f"http://{esp32_ip}/toggle_pid_control"
    # Add this new command handler in the send_command function
    elif command == "target":
        try:
            depth = input("Enter target depth in meters: ").strip()
            if not depth or not depth.replace('.', '', 1).isdigit():
                print("Invalid input. Please enter a positive number.")
                return
                
            url = f"http://{esp32_ip}/set_target_depth?depth={depth}"
            response = requests.get(url, timeout=10)
            print("Response:", response.text)
            return
            
        except Exception as e:
            print("Error setting target depth:", e)
            return
    elif command == "interval":
        try:
            interval = input("Enter read interval in milliseconds: ").strip()
            if not interval or not interval.isdigit() or int(interval) <= 0:
                print("Invalid input. Please enter a positive number.")
                return
                    
            url = f"http://{esp32_ip}/set_read_interval?ms={interval}"
            response = requests.get(url, timeout=10)
            print("Response:", response.text)
            return
                
        except Exception as e:
            print("Error setting read interval:", e)
            return
    # Add to the send_command function
    elif command == "status":
        url = f"http://{esp32_ip}/status"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                status_data = response.json()
                
                # Format and print the status data in a readable way
                print("\n===== FLOAT STATUS =====")
                print(f"System: {'Started' if status_data['started'] else 'Stopped'}")
                print(f"Uptime: {status_data['uptime_seconds']} seconds")
                
                # WiFi section
                wifi = status_data['wifi']
                print(f"\nWiFi: {'CONNECTED' if wifi['connected'] else 'DISCONNECTED'}")
                print(f"  Signal: {wifi['rssi']} dBm ({'Good' if wifi['good_signal'] else 'Poor'})")
                print(f"  IP: {wifi['ip']}")
                
                # Queue status
                queue = status_data['queue']
                print(f"\nQueue: {queue['current_size']}/{queue['capacity']} ({queue['percent_full']}% full)")
                print(f"  Read Interval: {queue['read_interval_ms']} ms")
                
                # Depth info
                depth = status_data['depth']
                print(f"\nDepth:")
                print(f"  Current: {depth['current']:.3f} m")
                print(f"  Target: {depth['target']:.3f} m ± {depth['tolerance']:.3f} m")
                print(f"  Pressure: {depth['pressure']:.2f} mbar")
                
                # Velocity
                velocity = status_data['velocity']
                print(f"\nVelocity:")
                print(f"  Current: {velocity['current']:.3f} m/s")
                print(f"  Limits: {velocity['max_descent']:.3f} m/s descent, {velocity['max_ascent']:.3f} m/s ascent")
                
                # PID parameters
                pid = status_data['pid']
                print(f"\nPID Control: {'ACTIVE' if pid['active'] else 'INACTIVE'}")
                print(f"  Parameters: Kp={pid['kp']}, Ki={pid['ki']}, Kd={pid['kd']}")
                print(f"  Last Output: {pid['last_output']}")
                print(f"  Last Error: {pid['last_error']:.3f}")
                print(f"  Integral: {pid['integral']:.3f}")
                
                # Routine status
                routine = status_data['routine']
                print(f"\nRoutine: {'ACTIVE' if routine['active'] else 'INACTIVE'}")
                print(f"  State: {routine['state']}")
                print(f"  Wait Time: {routine['wait_time_seconds']} seconds")
                
                if routine['active'] and routine['state'] == "waiting":
                    print(f"  Wait Progress: {routine['wait_elapsed_seconds']} / {routine['wait_time_seconds']} s")
                    print(f"  Remaining: {routine['wait_remaining_seconds']} s")
                
                # Pump status
                pump = status_data['pump']
                print(f"\nPump: {pump['state'].upper()}")
                
                print("=======================\n")
            else:
                print(f"Error getting status: {response.status_code}")
                print(response.text)
        except Exception as e:
            print(f"Error retrieving status: {e}")
        
    else:
        print("Invalid command!")
        return
    
    try:
        response = requests.get(url, timeout=10)
        print("Response:", response.text)
    except Exception as e:
        print("Error sending command:", e)

def main():
    esp32_ip = "192.168.1.226"  # Replace with your ESP32 IP if needed
    laptop_ip = get_laptop_ip()
    print(f"Laptop IP determined as: {laptop_ip}\n")
    print("Available Commands:")
    print("  s   - Start float")
    print("  vs  - Start velocity testing")
    print("  vst - Stop velocity testing")
    print("  st  - Stop float (and pump)")
    print("  rs  - Start routine (descend to >=TARGET DEPTH, hold > Routine Wait time, then ascend)")
    print("  a   - Float Ascend")
    print("  d   - Float Descend")
    print("  .   - Pump stop")
    print("  pid - Set PID parameters")
    print("  vel - Set velocity limits")
    print("  wait - Set routine wait time (in seconds)")
    print("  pid_toggle - Toggle PID control outside of routine mode")
    print("  routine_pid - Toggle PID control during routine wait phase") 
    print("  target - Set target depth for PID control")
    print("  interval - Set data read interval (in milliseconds)")
    print("  status - Get comprehensive system status")
    print("  q   - Quit")

    while True:
        cmd = input("Enter command: ").strip().lower()
        if cmd == "q":
            print("Exiting.")
            break
        send_command(esp32_ip, cmd, laptop_ip)

if __name__ == '__main__':
    main()