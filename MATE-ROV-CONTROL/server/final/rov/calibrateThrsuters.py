from smbus2 import SMBus
from time import sleep
import time

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
        self.MIN_PULSE = 500
        self.MAX_PULSE = 2500
        # Each ESC starts at the 1500µs neutral pulse
        self.current_pulse = self.STOP_PULSE

    def initialize(self):
        # Send neutral (1500µs) to let the ESC beep & detect
        self._set_pulse_width(self.STOP_PULSE)
        sleep(0.1)
        print(f"ESC on channel {self.channel} initialized with neutral signal")

    def set_pulse(self, pulse_width):
        if pulse_width == self.current_pulse:
            return  # No need to re-send if unchanged
        
        self.current_pulse = pulse_width
        self._set_pulse_width(pulse_width)

    def _set_pulse_width(self, pulse_width):
        offset = 9  # Your calibration offset
        pulse_width += offset
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        print(f"Channel {self.channel}: pulse {pulse_width} µs -> duty_cycle {duty_cycle}")
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        # A tiny pause can help the PCA9685 register the new duty cycle
        time.sleep(0.001)

def main():
    # Initialize PCA9685
    pca = PCA9685(bus_number=7)
    pca.frequency = 50
    
    # Define all 16 possible channels
    all_channels = list(range(16))
    
    # Create ESC objects for all channels
    esc_dict = {channel: ESC(channel, pca) for channel in all_channels}
    
    # Initialize all ESCs to neutral (1500)
    print("Initializing all ESCs to neutral position (1500)...")
    for channel, esc in esc_dict.items():
        esc.initialize()
    
    sleep(2)  # Let ESCs initialize fully
    print("All ESCs initialized to neutral. Ready for testing.")
    print("\nCommands:")
    print("  <channel>: Test the specified channel at 1700 pulse width")
    print("  <channel> <pulse>: Test the specified channel with custom pulse width (1100-1900)")
    print("  <channel>.stop: Stop the specified channel (back to 1500)")
    print("  s: Stop ALL channels (emergency stop)")
    print("  quit: Exit the program")
    
    try:
        while True:
            cmd = input("\nEnter command: ").strip().lower()
            
            if cmd == "quit":
                break
            
            # New command to stop all motors
            elif cmd == "s":
                print("EMERGENCY STOP - Setting all ESCs to neutral...")
                for channel, esc in esc_dict.items():
                    esc.set_pulse(1500)
                print("All motors stopped.")
                
            elif "." in cmd:
                parts = cmd.split(".")
                if len(parts) == 2 and parts[0].isdigit() and parts[1] == "stop":
                    channel = int(parts[0])
                    if 0 <= channel <= 15:
                        print(f"Stopping channel {channel}")
                        esc_dict[channel].set_pulse(1500)
                    else:
                        print("Invalid channel number. Use 0-15.")
            elif " " in cmd:  # Check for channel and pulse format
                parts = cmd.split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    channel = int(parts[0])
                    pulse = int(parts[1])
                    if 0 <= channel <= 5:
                        if 500 <= pulse <= 2500:
                            print(f"Testing channel {channel} at {pulse} pulse width")
                            esc_dict[channel].set_pulse(pulse)
                        else:
                            print("Invalid pulse width. Use values between 1100-1900.")
                    else:
                        print("Invalid channel number. Use 0-15.")
                else:
                    print("Invalid command format. Use '<channel> <pulse>'")
            elif cmd.isdigit():
                channel = int(cmd)
                if 0 <= channel <= 15:
                    print(f"Testing channel {channel} at 1700 pulse width")
                    esc_dict[channel].set_pulse(1100)
                else:
                    print("Invalid channel number. Use 0-15.")
            else:
                print("Invalid command")
                
    except KeyboardInterrupt:
        print("\nCalibration interrupted by user")
    finally:
        # Set all channels back to neutral before exiting
        print("Setting all ESCs back to neutral...")
        for channel, esc in esc_dict.items():
            esc.set_pulse(1500)
        sleep(0.5)
        pca.deinit()
        print("Done. All ESCs set to neutral and PCA9685 closed.")

if __name__ == '__main__':
    main()
#esc_channels = [12, 7, 6, 8, 9, 10, 13, 11]
#esc_channels = [13, 9, 10, 8, 11, 14, 15, 12]
#esc_channels = [9, 10, 7, 11, 6, 8, 13, 12]
# self.thruster_names = [
#     "FrontLeft", "FrontRight", "BackLeft", "BackRight",
#     "FrontLeftUp", "FrontRightUp", "BackRightUp", "BackLeftUp"
# ]