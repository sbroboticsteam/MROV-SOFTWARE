from adafruit_pca9685 import PCA9685
from board import SCL, SDA
import busio
from time import sleep

import socket
import sys
import os
import json

class ESC:
    def __init__(self, channel, pca):
        """
        Initializes an individual ESC.
        :param channel: PCA9685 channel used for the ESC's PWM signal.
        :param pca: The PCA9685 instance.
        """
        self.channel = channel
        self.pca = pca
        # PWM constants for ESC (in microseconds)
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1100  # Full reverse
        self.MAX_PULSE = 1900  # Full forward
        self.FORWARD_MIN = 1525
        self.REVERSE_MAX = 1475
        
    def initialize(self):
        """
        Initialize the ESC with a 1500μs pulse.
        """
        self._set_pulse_width(self.STOP_PULSE)
        sleep(2)  # Allow time for ESC to recognize the initialization signal
        print(f"ESC on channel {self.channel} initialized")
    
    def set_state(self, state):
        """
        Sets the ESC state based on the given value.
        :param state: A float between -1.0 and 1.0. Positive values indicate forward motion,
                      negative values indicate reverse, and zero stops the ESC.
        """
        if state > 0:
            # Forward: map 0->1 to FORWARD_MIN->MAX_PULSE
            pulse_width = self.FORWARD_MIN + (state * (self.MAX_PULSE - self.FORWARD_MIN))
        elif state < 0:
            # Reverse: map -1->0 to MIN_PULSE->REVERSE_MAX
            pulse_width = self.MIN_PULSE + (abs(state) * (self.REVERSE_MAX - self.MIN_PULSE))
        else:
            # Stop
            pulse_width = self.STOP_PULSE
            
        self._set_pulse_width(pulse_width)

    def _set_pulse_width(self, pulse_width):
        """
        Sets the PWM pulse width in microseconds.
        :param pulse_width: Desired pulse width in microseconds (1100-1900).
        """
        # PCA9685 works with duty cycle values from 0 to 0xFFFF
        # Convert microseconds to duty cycle
        # For 50Hz PWM frequency, a period is 20,000 microseconds
        # So the duty cycle is (pulse_width / 20,000)
        duty_cycle = int((pulse_width / 20000.0) * 0xFFFF)
        self.pca.channels[self.channel].duty_cycle = duty_cycle

class ESCController:
    def __init__(self, esc_channels, pca):
        """
        Initializes a collection of ESC objects.
        :param esc_channels: A list of channel numbers for the ESCs.
        :param pca: The PCA9685 instance to be used by all ESCs.
        """
        self.escs = []
        for channel in esc_channels:
            esc = ESC(channel, pca)
            self.escs.append(esc)
        
    def initialize_all(self):
        """
        Initializes all ESCs.
        """
        print("Initializing all ESCs...")
        for esc in self.escs:
            esc.initialize()
        print("All ESCs initialized.")

    def set_all_states(self, states):
        """
        Updates all ESCs based on the list of state values.
        :param states: A list of numbers (each between -1.0 and 1.0).
        """
        if len(states) != len(self.escs):
            print(f"Expected {len(self.escs)} states, got {len(states)}")
            return
        for esc, state in zip(self.escs, states):
            esc.set_state(state)

    def stop_all(self):
        """Stops all ESCs by sending the stop signal (1500μs)."""
        for esc in self.escs:
            esc.set_state(0)

def main():
    # ESC configuration - channel numbers for each ESC
    esc_channels = [8, 9, 10, 11, 12, 13, 14, 15]  # Channels for 8 ESCs

    # Set up I2C and initialize PCA9685
    i2c = busio.I2C(SCL, SDA)
    pca = PCA9685(i2c)
    # Set PWM frequency to 50Hz (standard for most ESCs)
    pca.frequency = 50

    # Initialize ESC controller with the channel configurations
    esc_controller = ESCController(esc_channels, pca)
    
    # Initialize all ESCs before use
    esc_controller.initialize_all()
    
    HOST = '192.168.1.130'  # Replace with your Raspberry Pi's IP address
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
                    print(f"PRINT MOTORS: {motor_states}")
                    # First 4 values control motors responsible for front, back, left, right, last 4 values control motors responsible for up, down. 
                    if isinstance(motor_states, list) and len(motor_states) == 8:
                    # Update ESC states with the received motor values.
                        esc_controller.set_all_states(motor_states)
                        print("hello")
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
        esc_controller.stop_all()
        pca.deinit()
        server.close()
        print("Server closed and motors stopped.")

if __name__ == '__main__':
    main()
    