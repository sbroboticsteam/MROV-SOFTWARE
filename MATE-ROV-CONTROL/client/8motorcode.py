import socket
import json
from adafruit_pca9685 import PCA9685
from board import SCL, SDA
import busio
from gpiozero import OutputDevice
from time import sleep

# Define motor GPIO pin mappings for IN1 and IN2
motor_pins = [
    {"IN1": 4, "IN2": 17, "ENABLE": 8},  # Motor 1 (ENABLE on PCA9685 channel 0) front left
    {"IN1": 27, "IN2": 22, "ENABLE": 9},  # Motor 2 (ENABLE on PCA9685 channel 1) front right
    {"IN1": 10, "IN2": 9, "ENABLE": 10},   # Motor 3 (ENABLE on PCA9685 channel 2) back left
    {"IN1": 11, "IN2": 5, "ENABLE": 11},   # Motor 4 (ENABLE on PCA9685 channel 3) back right
    {"IN1": 6, "IN2": 13, "ENABLE": 12},   # Motor 5 (ENABLE on PCA9685 channel 4)
    {"IN1": 19, "IN2": 26, "ENABLE":13},  # Motor 6 (ENABLE on PCA9685 channel 5)
    {"IN1": 21, "IN2": 20, "ENABLE": 14},  # Motor 7 (ENABLE on PCA9685 channel 6)
    {"IN1": 16, "IN2": 12, "ENABLE": 15}   # Motor 8 (ENABLE on PCA9685 channel 7)
]

# Initialize GPIO pins for motors using gpiozero
motors = []
for pins in motor_pins:
    motors.append({
        "IN1": OutputDevice(pins["IN1"]),
        "IN2": OutputDevice(pins["IN2"]),
        "ENABLE": pins["ENABLE"]  # PCA9685 channel
    })

# Set up I2C and PCA9685
i2c = busio.I2C(SCL, SDA)
pca = PCA9685(i2c)
pca.frequency = 100  # Set PWM frequency to 100 Hz

# Function to control motor speed and direction
def set_motor_state(motor, state):
    """
    Control motor state based on the input value.
    :param motor: Motor dictionary with IN1, IN2, and ENABLE pins.
    :param state: Speed and direction (-1.0 to 1.0).
    """
    if state > 0:
        # Forward
        motor["IN1"].on()
        motor["IN2"].off()
        set_motor_speed(motor["ENABLE"], state * 100)
    elif state < 0:
        # Reverse
        motor["IN1"].off()
        motor["IN2"].on()
        set_motor_speed(motor["ENABLE"], abs(state) * 100)
    else:
        # Stop
        motor["IN1"].off()
        motor["IN2"].off()
        set_motor_speed(motor["ENABLE"], 0)

# Function to set motor speed using PCA9685
def set_motor_speed(channel, speed):
    """
    Set motor speed using PCA9685.
    :param channel: PCA9685 channel for motor enable pin.
    :param speed: Speed (0 to 100%).
    """
    duty_cycle = int(0xFFFF * (speed / 100))  # Convert speed percentage to 16-bit value
    pca.channels[channel].duty_cycle = duty_cycle

# Server setup
HOST = '192.168.0.160'  # Replace with your Raspberry Pi's IP address
PORT = 4891

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(5)

print(f"Server listening on {HOST}:{PORT}...")

try:
    while True:
        com_socket, addy = server.accept()
        print(f"Connected to {addy}")
        
        while True:
            data = com_socket.recv(1024)
            if not data:
                break

            motor_values = data.decode('utf-8')
            print(f"Received motor values: {motor_values}")

            try:
                # Replace single quotes with double quotes for valid JSON
                motor_values_json = motor_values.replace("'", '"')

                # Parse the corrected JSON string
                motor_values_dict = json.loads(motor_values_json)
                
                # Ensure `motor_values` is a list
                motor_states = motor_values_dict['motor_values']  # Should be a list of 8 values (e.g., [-1, 1, 0, 0, 1, -1, 0, 1])
                # First 4 values control motors responsible for front, back, left, right, last 4 values control motors responsible for up, down. 
                if isinstance(motor_states, list) and len(motor_states) == 8:
                    for motor, state in zip(motors, motor_states):
                        set_motor_state(motor, state)
                else:
                    print("Invalid motor values format. Expected a list of 8 floats/integers.")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error parsing motor values: {e}")

        com_socket.send(f"Message received".encode('utf-8'))
        com_socket.close()
        print(f"Connection with {addy} ended.")
except KeyboardInterrupt:
    print("Server is shutting down...")
finally:
    # Stop all motors and clean up
    for motor in motors:
        set_motor_state(motor, 0)  # Stop motor
    pca.deinit()
    server.close()
    print("Server closed and motors stopped.")
