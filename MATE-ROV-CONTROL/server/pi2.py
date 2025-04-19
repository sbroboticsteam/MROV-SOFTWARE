import socket
import sys
import os
import json
import time

# Try to import from current directory first, then try src directory
try:
    from controller import get_controller_input
except ImportError:
    try:
        # Add the src directory to the Python path
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
        from controller import get_controller_input
    except ImportError:
        print("ERROR: Could not import get_controller_input from controller.py.")
        print("Ensure controller.py is in the current directory or ../src relative to this script.")
        sys.exit(1)

# --- Configuration ---
HOST = '192.168.1.237'  # IP address of the Raspberry Pi (Jetson) running the server
PORT = 4891
RECONNECT_DELAY = 5  # Seconds to wait before attempting to reconnect
SEND_INTERVAL = 0.05 # Seconds between sending updates (approx 20 Hz)

# --- Button Mapping (Example - Adjust based on your controller) ---
# Use pygame.joystick documentation or a test script to find button indices
PID_TOGGLE_BUTTON_INDEX = 3  # Example: 'Y' button on Xbox controller
RESET_HEADING_BUTTON_INDEX = 0 # Example: 'A' button on Xbox controller

def main():
    print("Client starting...")
    print(f"Attempting to connect to server at {HOST}:{PORT}")

    # Initialize state for button presses
    last_pid_button_state = 0
    last_reset_button_state = 0
    pid_enabled_on_server = True # Assume PID starts enabled on server (matches server code)

    try:
        # Initialize the controller input generator
        controller_generator = get_controller_input()
        print("Controller input generator initialized.")
    except Exception as e:
        print(f"Error initializing controller: {e}")
        return # Exit if controller fails

    while True:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client_socket.connect((HOST, PORT))
            print(f"Connected to server at {HOST}:{PORT}")
            last_data_sent = None # Keep track of the last sent data to avoid redundant sends

            while True:
                start_time = time.time()

                # --- Get Controller Input ---
                try:
                    inputs = next(controller_generator)
                except StopIteration:
                    print("Controller input generator finished unexpectedly.")
                    break # Exit inner loop if generator stops
                except Exception as e:
                    print(f"Error getting controller input: {e}")
                    time.sleep(0.1) # Wait a bit before retrying
                    continue # Skip this iteration

                # --- Check for PID Commands ---
                pid_toggle_cmd = False
                reset_heading_cmd = False

                # --- Check for PID Commands ---
                pid_toggle_cmd = False
                reset_heading_cmd = False

                # Only check button states if 'buttons' exists in inputs
                if 'buttons' in inputs:
                    # Check PID Toggle Button (Button 3 / 'Y')
                    current_pid_button_state = inputs['buttons'][PID_TOGGLE_BUTTON_INDEX]
                    if current_pid_button_state == 1 and last_pid_button_state == 0:
                        pid_toggle_cmd = True
                        pid_enabled_on_server = not pid_enabled_on_server # Toggle local assumption
                        print(f"Button {PID_TOGGLE_BUTTON_INDEX} pressed: Sending PID Toggle command. Assumed server state: {'Enabled' if pid_enabled_on_server else 'Disabled'}")
                    last_pid_button_state = current_pid_button_state

                    # Check Reset Heading Button (Button 0 / 'A')
                    current_reset_button_state = inputs['buttons'][RESET_HEADING_BUTTON_INDEX]
                    if current_reset_button_state == 1 and last_reset_button_state == 0:
                        reset_heading_cmd = True
                        print(f"Button {RESET_HEADING_BUTTON_INDEX} ('A') pressed: Sending Reset Heading command.")
                    last_reset_button_state = current_reset_button_state
                else:
                    # If 'buttons' key is missing, log it once (not every iteration)
                    if last_data_sent is None:  # Only log on first iteration or after reconnect
                        print("Warning: 'buttons' data not available from controller input")
                

                # --- Prepare Data ---
                # Only include motor_values and any active commands
                data_to_send = {
                    "motor_values": inputs.get("motor_values", [0.0] * 8) # Get motor values or default
                }
                if pid_toggle_cmd:
                    data_to_send["pid_toggle"] = True # Send command to toggle server state
                if reset_heading_cmd:
                    data_to_send["reset_heading"] = True # Send command to reset heading

                # --- Send Data if Changed ---
                # Convert to a comparable format (e.g., sorted tuple of items)
                current_data_comparable = tuple(sorted(data_to_send.items()))

                if current_data_comparable != last_data_sent:
                    try:
                        json_data = json.dumps(data_to_send)
                        client_socket.sendall(json_data.encode('utf-8'))
                        # print(f"Sent: {json_data}") # Uncomment for debugging
                        last_data_sent = current_data_comparable
                    except socket.error as e:
                        print(f"Socket error during send: {e}. Disconnecting.")
                        break # Exit inner loop on send error
                    except Exception as e:
                        print(f"Error sending data: {e}")
                        break # Exit inner loop on other send errors

                # --- Control Send Rate ---
                elapsed_time = time.time() - start_time
                sleep_time = SEND_INTERVAL - elapsed_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except socket.error as e:
            print(f"Socket connection error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            client_socket.close()
            print(f"Connection closed. Waiting {RECONNECT_DELAY} seconds before reconnecting...")
            # Reset button states on disconnect to avoid sending stale commands on reconnect
            last_pid_button_state = 0
            last_reset_button_state = 0
            last_data_sent = None
            time.sleep(RECONNECT_DELAY)

if __name__ == "__main__":
    main()