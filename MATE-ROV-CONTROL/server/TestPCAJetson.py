from smbus2 import SMBus
from time import sleep
import socket
import sys
import os
import json

# PCA9685 constants
PCA9685_ADDRESS = 0x40  # Default I2C address
MODE1 = 0x00
MODE2 = 0x01
PRESCALE = 0xFE
LED0_ON_L = 0x06


class PCA9685:
    def __init__(self, bus_number=7, address=PCA9685_ADDRESS):
        self.bus = SMBus(bus_number)
        self.address = address
        self.channels = [PCA9685Channel(self, i) for i in range(16)]
        self.reset()

    def reset(self):
        self.bus.write_byte_data(self.address, MODE1, 0x00)  # Normal mode
        sleep(0.01)  # Wait for reset

    @property
    def frequency(self):
        return self._frequency

    @frequency.setter
    def frequency(self, freq_hz):
        self._frequency = freq_hz
        prescale_val = int(25000000.0 / (4096 * freq_hz)) - 1

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


# Example usage:
if __name__ == "__main__":
    # ESC configuration - channel numbers for each ESC
    esc_channels = [8, 9, 10, 11, 12, 13, 14, 15]  # Channels for 8 ESCs

    # Initialize PCA9685 with I2C bus 7
    pca = PCA9685(bus_number=7)

    # Set PWM frequency to 50Hz (standard for most ESCs)
    pca.frequency = 50

    # Example: set neutral duty cycle to all ESCs (1500us pulse)
    # 1500us -> 307 (~1500 / 20000 * 4096)
    neutral_duty = int((1500 / 20000.0) * 4096)

    for ch in esc_channels:
        pca.channels[ch].duty_cycle = neutral_duty
        print(f"ESC on channel {ch} set to neutral")

    print("All ESCs initialized.")
