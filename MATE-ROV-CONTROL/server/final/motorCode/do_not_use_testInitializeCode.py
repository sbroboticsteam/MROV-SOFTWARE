import socket
import json
from adafruit_pca9685 import PCA9685
from board import SCL, SDA
import busio
from gpiozero import OutputDevice
from time import sleep

class Motor:
    def __init__(self, in1_pin, in2_pin, enable_channel, pca):
        """
        Initializes an individual motor.
        :param in1_pin: GPIO pin for IN1.
        :param in2_pin: GPIO pin for IN2.
        :param enable_channel: PCA9685 channel used for the motor's enable (PWM) signal.
        :param pca: The PCA9685 instance.
        """
        self.in1 = OutputDevice(in1_pin)
        self.in2 = OutputDevice(in2_pin)
        self.enable_channel = enable_channel
        self.pca = pca

    def set_state(self, state):
        """
        Sets the motor state based on the given value.
        :param state: A float between -1.0 and 1.0. Positive values indicate forward motion,
                      negative values indicate reverse, and zero stops the motor.
        """
        if state > 0:
            self.in1.on()
            self.in2.off()
            self._set_speed(state)
        elif state < 0:
            self.in1.off()
            self.in2.on()
            self._set_speed(abs(state))
        else:
            self.in1.off()
            self.in2.off()
            self._set_speed(0)

    def _set_speed(self, speed):
        """
        Converts a normalized speed value (0 to 1) to a duty cycle and applies it via PCA9685.
        :param speed: A float between 0 and 1.
        """
        # Convert to percentage and then to a 16-bit duty cycle value.
        percentage = speed * 100
        duty_cycle = int(0xFFFF * (percentage / 100))
        self.pca.channels[self.enable_channel].duty_cycle = duty_cycle

class MotorController:
    def __init__(self, motor_configs, pca):
        """
        Initializes a collection of Motor objects.
        :param motor_configs: A list of dictionaries containing pin configurations.
        :param pca: The PCA9685 instance to be used by all motors.
        """
        self.motors = []
        for config in motor_configs:
            motor = Motor(config["IN1"], config["IN2"], config["ENABLE"], pca)
            self.motors.append(motor)

    def set_all_states(self, states):
        """
        Updates all motors based on the list of state values.
        :param states: A list of 8 numbers (each between -1.0 and 1.0).
        """
        if len(states) != len(self.motors):
            print(f"Expected {len(self.motors)} states, got {len(states)}")
            return
        for motor, state in zip(self.motors, states):
            motor.set_state(state)

    def stop_all(self):
        """Stops all motors."""
        for motor in self.motors:
            motor.set_state(0)

class MotorServer:
    def __init__(self, host, port, motor_controller):
        """
        Sets up the socket server for receiving motor commands.
        :param host: IP address for the server.
        :param port: Port number for the server.
        :param motor_controller: The MotorController instance.
        """
        self.host = host
        self.port = port
        self.motor_controller = motor_controller
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(5)
        print(f"Server listening on {self.host}:{self.port}...")

    def run(self):
        """
        Main loop for accepting connections and handling incoming data.
        """
        try:
            while True:
                client_socket, addr = self.server.accept()
                print(f"Connected to {addr}")
                self.handle_client(client_socket)
        except KeyboardInterrupt:
            print("Server is shutting down...")
        finally:
            self.motor_controller.stop_all()
            self.server.close()
            print("Server closed and motors stopped.")

    def handle_client(self, client_socket):
        """
        Processes commands from a connected client.
        """
        with client_socket:
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break

                motor_values = data.decode('utf-8')
                print(f"Received motor values: {motor_values}")

                try:
                    # Ensure valid JSON (replace single quotes with double quotes)
                    motor_values_json = motor_values.replace("'", '"')
                    data_dict = json.loads(motor_values_json)
                    # 'motor_values' should be a list of 8 numbers (e.g., [-1, 1, 0, 0, 1, -1, 0, 1])
                    states = data_dict['motor_values']
                    if isinstance(states, list) and len(states) == len(self.motor_controller.motors):
                        self.motor_controller.set_all_states(states)
                    else:
                        print("Invalid motor values format. Expected a list of 8 numbers.")
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Error parsing motor values: {e}")
            client_socket.send("Message received".encode('utf-8'))
            print("Connection closed.")

def main():
    # Motor configuration for 8 motors.
    motor_configs = [
        {"IN1": 4,  "IN2": 17, "ENABLE": 8},   # Motor 1
        {"IN1": 27, "IN2": 22, "ENABLE": 9},   # Motor 2
        {"IN1": 10, "IN2": 9,  "ENABLE": 10},  # Motor 3
        {"IN1": 11, "IN2": 5,  "ENABLE": 11},  # Motor 4
        {"IN1": 6,  "IN2": 13, "ENABLE": 12},  # Motor 5
        {"IN1": 19, "IN2": 26, "ENABLE": 13},  # Motor 6
        {"IN1": 21, "IN2": 20, "ENABLE": 14},  # Motor 7
        {"IN1": 16, "IN2": 12, "ENABLE": 15}   # Motor 8
    ]

    # Set up I2C and initialize PCA9685.
    i2c = busio.I2C(SCL, SDA)
    pca = PCA9685(i2c)
    pca.frequency = 100  # Set PWM frequency for all motors

    # Initialize motor controller with the motor configurations.
    motor_controller = MotorController(motor_configs, pca)

    # Set up and run the server.
    HOST = '192.168.0.160'  # Replace with your Raspberry Pi's IP address.
    PORT = 4891
    server = MotorServer(HOST, PORT, motor_controller)
    
    try:
        server.run()
    finally:
        # Ensure proper cleanup.
        motor_controller.stop_all()
        pca.deinit()
        print("PCA9685 deinitialized and cleanup complete.")

if __name__ == '__main__':
    main()
