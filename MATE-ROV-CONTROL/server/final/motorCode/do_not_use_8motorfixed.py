import time
import socket
import json
from smbus2 import SMBus

# Set the I2C address for the Pico (adjust as needed)
PICO_I2C_ADDRESS = 0x10

class PicoI2CDriver:
    def __init__(self, bus_number=7, address=PICO_I2C_ADDRESS):
        """
        Initialize the I²C connection to the Pico.
        On the Jetson Orin Nano, use the appropriate bus number (e.g. 7).
        """
        self.bus = SMBus(bus_number)
        self.address = address

    def set_frequency(self, channel, frequency):
        """
        Sends a command to the Pico to set the frequency on a given channel.
        The command format is 3 bytes:
          [channel (1 byte), frequency high byte, frequency low byte]
        Frequency is assumed to be an integer value (e.g. in Hz).
        """
        # Ensure frequency is an integer
        freq_int = int(frequency)
        high_byte = (freq_int >> 8) & 0xFF
        low_byte = freq_int & 0xFF
        payload = [channel, high_byte, low_byte]
        # Write the payload to the Pico starting at register 0x00.
        # (Your Pico firmware must interpret this correctly.)
        self.bus.write_i2c_block_data(self.address, 0x00, payload)
        # Optional: you can add a short delay here if needed.
        time.sleep(0.001)

    def close(self):
        """Close the I²C connection."""
        self.bus.close()


class MotorController:
    def __init__(self, channels, pico_driver):
        """
        channels: list of channel numbers (e.g. [0, 1, 2, ..., 7])
        pico_driver: an instance of PicoI2CDriver.
        """
        self.channels = channels
        self.pico = pico_driver

    def set_all_frequencies(self, freq_values):
        """
        Expects freq_values to be a list of frequency values, one per channel.
        Sends the corresponding command for each channel.
        """
        if len(freq_values) != len(self.channels):
            print(f"Expected {len(self.channels)} frequencies, got {len(freq_values)}")
            return

        for ch, freq in zip(self.channels, freq_values):
            self.pico.set_frequency(ch, freq)
            print(f"Channel {ch} set to {freq} Hz")


def main():
    # Define the 8 channels for the Pico.
    channels = list(range(8))
    
    # Initialize the PicoI2CDriver with bus 7 (Jetson Orin Nano) and the Pico's I²C address.
    pico_driver = PicoI2CDriver(bus_number=7, address=PICO_I2C_ADDRESS)
    
    # Create a MotorController that uses the Pico driver.
    motor_controller = MotorController(channels, pico_driver)
    
    # Set up a TCP server to receive motor frequency values.
    HOST = '192.168.1.173'
    PORT = 4891

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"Server listening on {HOST}:{PORT}...")

    try:
        while True:
            com_socket, addr = server.accept()
            print(f"Connected to {addr}")
            while True:
                data = com_socket.recv(1024)
                if not data:
                    break
                # Expecting JSON-formatted data with motor frequency values.
                # For example: {"motor_values": [1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700]}
                motor_values_str = data.decode('utf-8')
                print(f"Received motor values: {motor_values_str}")
                try:
                    # Replace single quotes with double quotes if necessary.
                    motor_values_json = motor_values_str.replace("'", '"')
                    motor_values_dict = json.loads(motor_values_json)
                    freq_values = motor_values_dict['motor_values']
                    if isinstance(freq_values, list) and len(freq_values) == len(channels):
                        motor_controller.set_all_frequencies(freq_values)
                        print("Motor frequencies updated")
                    else:
                        print("Invalid motor values format. Expected a list of 8 frequency values.")
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Error parsing motor values: {e}")
            com_socket.send("Message received".encode('utf-8'))
            com_socket.close()
            print(f"Connection with {addr} ended.")
    except KeyboardInterrupt:
        print("Server is shutting down...")
    finally:
        pico_driver.close()
        server.close()
        print("Server closed and connection to Pico terminated.")


if __name__ == '__main__':
    main()

