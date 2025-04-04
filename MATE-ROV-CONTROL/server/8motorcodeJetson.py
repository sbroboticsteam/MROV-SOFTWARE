from smbus2 import SMBus
from time import sleep
import socket
import json
import time
import select

# PCA9685 constants
PCA9685_ADDRESS = 0x40
MODE1 = 0x00
PRESCALE = 0xFE
LED0_ON_L = 0x06

class PCA9685:
    def __init__(self, bus_number=7, address=PCA9685_ADDRESS):
        self.bus = SMBus(bus_number)
        self.address = address
        self.channels = [PCA9685Channel(self, i) for i in range(16)]
        self.reset()

    def reset(self):
        self.bus.write_byte_data(self.address, MODE1, 0x00)
        sleep(0.01)

    @property
    def frequency(self):
        return self._frequency

    @frequency.setter
    def frequency(self, freq_hz):
        # Adjust requested frequency to compensate for chip inaccuracy
        # For 666Hz target, request around 630Hz
        adjusted_freq = int(freq_hz * 0.95)  # Adjust by 5% down
        self._frequency = freq_hz
        prescale_val = int(25000000.0 / (4096 * adjusted_freq)) - 1

        mode1 = self.bus.read_byte_data(self.address, MODE1)
        self.bus.write_byte_data(self.address, MODE1, (mode1 & 0x7F) | 0x10)
        self.bus.write_byte_data(self.address, PRESCALE, prescale_val)
        self.bus.write_byte_data(self.address, MODE1, mode1)
        sleep(0.005)
        self.bus.write_byte_data(self.address, MODE1, mode1 | 0x80)

    def deinit(self):
        try:
            self.bus.close()
        except:
            pass

class PCA9685Channel:
    def __init__(self, pca, channel):
        self.pca = pca
        self.channel = channel
        self._duty_cycle = 0

    @property
    def duty_cycle(self):
        return self._duty_cycle

    @duty_cycle.setter
    def duty_cycle(self, value):
        self._duty_cycle = value
        on_value = 0
        off_value = value & 0xFFFF
        base_reg = LED0_ON_L + (4 * self.channel)

        self.pca.bus.write_byte_data(self.pca.address, base_reg, on_value & 0xFF)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 1, (on_value >> 8) & 0xFF)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 2, off_value & 0xFF)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 3, (off_value >> 8) & 0xFF)

class ESC:
    def __init__(self, channel, pca):
        self.channel = channel
        self.pca = pca
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1100
        self.MAX_PULSE = 1900
        self.FORWARD_MIN = 1525
        self.REVERSE_MAX = 1475

    def initialize(self):
        self._set_pulse_width(self.STOP_PULSE)
        sleep(2)
        print(f"ESC on channel {self.channel} initialized")

    def set_state(self, state):
        if state > 0:
            # Forward: map 0->1 to FORWARD_MIN->MAX_PULSE (1525->1900)
            pulse_width = self.FORWARD_MIN + (state * (self.MAX_PULSE - self.FORWARD_MIN))
        elif state < 0:
            print("RIGHT Trigger")
            # Reverse: map -1->0 to MIN_PULSE->REVERSE_MAX (1100->1475)
            # The current formula gives 1475 for full reverse, not 1100
            pulse_width = self.REVERSE_MAX - (abs(state) * (self.REVERSE_MAX - self.MIN_PULSE))
        else:
            # Stop at 1500μs
            pulse_width = self.STOP_PULSE
	    
        # print(pulse_width)
        self._set_pulse_width(pulse_width)

    def _set_pulse_width(self, pulse_width):
        duty_cycle = int((pulse_width / 20000.0) * 0xFFFF)
        print(duty_cycle)
        self.pca.channels[self.channel].duty_cycle = duty_cycle

class ESCController:
    def __init__(self, esc_channels, pca):
        self.escs = [ESC(channel, pca) for channel in esc_channels]

    def initialize_all(self):
        print("Initializing all ESCs...")
        for esc in self.escs:
            esc.initialize()
        print("All ESCs initialized.")

    def set_all_states(self, states):
        if len(states) != len(self.escs):
            print(f"Expected {len(self.escs)} states, got {len(states)}")
            return
        for esc, state in zip(self.escs, states):
            # print(states)
            esc.set_state(state)

    def stop_all(self):
        for esc in self.escs:
            esc.set_state(0)

def main():
    esc_channels = [8, 9, 10, 11, 12, 13, 14, 15]
    pca = PCA9685(bus_number=7)
    pca.frequency = 50

    esc_controller = ESCController(esc_channels, pca)
    esc_controller.initialize_all()

    HOST = '192.168.1.173'
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
                    motor_values_json = motor_values.replace("'", '"')
                    motor_values_dict = json.loads(motor_values_json)
                    motor_states = motor_values_dict['motor_values']

                    if isinstance(motor_states, list) and len(motor_states) == 8:
                        esc_controller.set_all_states(motor_states)
                        print("ESCs updated")
                    else:
                        print("Invalid motor values format. Expected a list of 8 floats/integers.")
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Error parsing motor values: {e}")

            com_socket.send("Message received".encode('utf-8'))
            com_socket.close()
            print(f"Connection with {addy} ended.")

    except KeyboardInterrupt:
        print("Server is shutting down...")
    finally:
        esc_controller.stop_all()
        pca.deinit()
        server.close()
        print("Server closed and motors stopped.")

if __name__ == '__main__':
    main()
