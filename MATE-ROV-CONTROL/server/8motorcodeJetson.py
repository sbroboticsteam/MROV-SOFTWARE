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
        self._frequency = freq_hz
        prescale_val = int(25000000.0 / (4096 * freq_hz)) - 1

        mode1 = self.bus.read_byte_data(self.address, MODE1)
        # Enter sleep mode
        self.bus.write_byte_data(self.address, MODE1, (mode1 & 0x7F) | 0x10)
        sleep(0.001)  # micro-delay
        self.bus.write_byte_data(self.address, PRESCALE, prescale_val)
        sleep(0.001)  # micro-delay
        # Exit sleep mode
        self.bus.write_byte_data(self.address, MODE1, mode1)
        sleep(0.005)
        # Restart
        self.bus.write_byte_data(self.address, MODE1, mode1 | 0x80)
        sleep(0.001)  # micro-delay

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

        # Write each register with a small delay
        self.pca.bus.write_byte_data(self.pca.address, base_reg, on_value & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 1, (on_value >> 8) & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 2, off_value & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 3, (off_value >> 8) & 0xFF)
        time.sleep(0.001)

class ESC:
    def __init__(self, channel, pca):
        self.channel = channel
        self.pca = pca
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1100
        self.MAX_PULSE = 1900
        self.FORWARD_MIN = 1525
        self.REVERSE_MAX = 1475
        # Each ESC starts at the 1500µs neutral pulse
        self.current_pulse = self.STOP_PULSE

    def initialize(self):
        # Send neutral (1500µs) to let the ESC beep & detect
        self._set_pulse_width(self.STOP_PULSE)
        sleep(2)
        print(f"ESC on channel {self.channel} initialized")

    def set_state(self, state):
        # If state>0 => forward from 1525 to 1900;
        # if state<0 => reverse from 1475 down to 1100;
        # else => neutral 1500
        if state > 0:
            pulse_width = self.FORWARD_MIN + (state * (self.MAX_PULSE - self.FORWARD_MIN))
        elif state < 0:
            pulse_width = self.REVERSE_MAX - (abs(state) * (self.REVERSE_MAX - self.MIN_PULSE))
        else:
            pulse_width = self.STOP_PULSE

        if pulse_width == self.current_pulse:
            return  # No need to re-send if unchanged
        

        self.current_pulse = pulse_width
        self._set_pulse_width(pulse_width)

    def _set_pulse_width(self, pulse_width):
        offset = 9
        pulse_width += offset
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        print(f"Channel {self.channel}: pulse {pulse_width} µs -> duty_cycle {duty_cycle}")
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        # A tiny pause can help the PCA9685 register the new duty cycle
        time.sleep(0.001)

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
            esc.set_state(state)

    def stop_all(self):
        for esc in self.escs:
            esc.set_state(0)

    def sendCustomPeriod(self, period):
        # Send a custom period to all ESCs
        for esc in self.escs:
            esc._set_pulse_width(period)

def main():
    esc_channels = [0, 1, 2, 3, 4, 5, 6, 7]
    pca = PCA9685(bus_number=7)
    pca.frequency = 50

    esc_controller = ESCController(esc_channels, pca)

    esc_controller.initialize_all()

    
    # motor_states = [-1, -1, 1, 1, 1,1,1,1]  # Example motor states
    # esc_controller.set_all_states(motor_states)

    # return

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
                        # Update all ESCs
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
        # Ensure the motors are stopped and bus is closed
        esc_controller.stop_all()
        pca.deinit()
        server.close()
        print("Server closed and motors stopped.")

if __name__ == '__main__':
    main()