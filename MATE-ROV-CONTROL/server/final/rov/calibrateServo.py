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

class Servo:
    def __init__(self, channel, pca):
        self.channel = channel
        self.pca = pca
        self.CENTER_PULSE = 1500  # Center position (90 degrees)
        self.MIN_PULSE = 500      # 0 degrees position
        self.MAX_PULSE = 2500     # 180 degrees position
        self.current_pulse = self.CENTER_PULSE
        self.initial_pulse = self.CENTER_PULSE  # Default initial position

    def initialize(self, initial_pulse=None):
        """Initialize the servo with an optional initial pulse width"""
        if initial_pulse is not None and self.MIN_PULSE <= initial_pulse <= self.MAX_PULSE:
            self.initial_pulse = initial_pulse
            
        # Set to the initial position
        self.set_pulse(self.initial_pulse)
        sleep(0.1)
        print(f"Servo on channel {self.channel} initialized at {self.initial_pulse}µs")
        
    def set_pulse(self, pulse_width):
        """Set the servo position using pulse width in microseconds"""
        if pulse_width == self.current_pulse:
            return  # No need to re-send if unchanged
            
        if not (self.MIN_PULSE <= pulse_width <= self.MAX_PULSE):
            print(f"Warning: Pulse width {pulse_width} outside of safe range ({self.MIN_PULSE}-{self.MAX_PULSE})")
            pulse_width = max(self.MIN_PULSE, min(self.MAX_PULSE, pulse_width))
            
        self.current_pulse = pulse_width
        self._set_pulse_width(pulse_width)
        
    def set_angle(self, angle):
        """Set the servo position using angle in degrees (0-180)"""
        if not (0 <= angle <= 180):
            print(f"Warning: Angle {angle} outside of range (0-180)")
            angle = max(0, min(180, angle))
            
        # Convert angle to pulse width: 0° = MIN_PULSE, 180° = MAX_PULSE
        pulse_width = self.MIN_PULSE + (angle / 180.0) * (self.MAX_PULSE - self.MIN_PULSE)
        self.set_pulse(int(pulse_width))
        
    def center(self):
        """Set the servo to its center position"""
        self.set_pulse(self.CENTER_PULSE)

    def _set_pulse_width(self, pulse_width):
        """Set the pulse width by calculating the appropriate duty cycle"""
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        print(f"Servo {self.channel}: pulse {pulse_width} µs -> duty_cycle {duty_cycle}")
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        time.sleep(0.001)  # Small delay for stability

def main():
    # Initialize PCA9685
    pca = PCA9685(bus_number=7)
    pca.frequency = 50  # 50Hz is standard for servos
    
    # Only use channels 2, 3, 4, and 5
    servo_channels = [0, 1, 2, 3, 4, 5]
    
    # Create Servo objects for the specified channels
    servo_dict = {channel: Servo(channel, pca) for channel in servo_channels}
    
    # Dictionary to name the servos (can be customized)
    servo_names = {
        5: "Gripper",
        4: "Wrist",
        3: "Elbow",
        2: "Shoulder"

        '''

        "wrist": Servo(4, pca, min_pulse=900, max_pulse=1950, name="Wrist"),
        "elbow": Servo(3, pca, min_pulse=675, max_pulse=1619, name="Elbow"),
        "shoulder": Servo(2, pca, min_pulse= 1200, max_pulse=1560, name="Shoulder"),
        "claw": Servo(5, pca, min_pulse=1175, max_pulse=1850, name="Claw")

        '''
    }
    
    # Initialize all servos to their center position by default
    print("Initializing servos...")
    
    # You can customize initial positions for each servo here
    initial_positions = {
        # Format: channel: initial_pulse_width
        # Example: 2: 1700,  # Initialize channel 2 to 1700μs
    }
    
    for channel, servo in servo_dict.items():
        initial_pulse = initial_positions.get(channel)
        servo.initialize(initial_pulse)
    
    sleep(1)  # Let servos initialize
    
    print("All servos initialized. Ready for testing.")
    print("\nCommands:")
    print("  <channel>: Move the specified servo to center position")
    print("  <channel> <pulse>: Set the specified servo to custom pulse width (500-2500μs)")
    print("  <channel>.angle <angle>: Set the servo to angle in degrees (0-180)")
    print("  <channel>.init <pulse>: Change the initial position of a servo")
    print("  center: Center all servos")
    print("  quit: Exit the program")
    
    try:
        while True:
            cmd = input("\nEnter command: ").strip().lower()
            
            if cmd == "quit":
                break
                
            elif cmd == "center":
                print("Centering all servos...")
                for channel, servo in servo_dict.items():
                    servo.center()
                    
            elif "." in cmd:
                parts = cmd.split(".")
                if len(parts) == 2 and parts[0].isdigit():
                    channel = int(parts[0])
                    if channel not in servo_channels:
                        print(f"Invalid channel. Use one of: {servo_channels}")
                        continue
                        
                    if parts[1].startswith("angle "):
                        try:
                            angle = float(parts[1].split()[1])
                            print(f"Setting {servo_names.get(channel, f'Servo {channel}')} to {angle}°")
                            servo_dict[channel].set_angle(angle)
                        except (ValueError, IndexError):
                            print("Invalid angle value. Use a number between 0-180.")
                            
                    elif parts[1].startswith("init "):
                        try:
                            pulse = int(parts[1].split()[1])
                            if 500 <= pulse <= 2500:
                                print(f"Changing initial position of {servo_names.get(channel, f'Servo {channel}')} to {pulse}µs")
                                servo_dict[channel].initial_pulse = pulse
                                servo_dict[channel].set_pulse(pulse)
                            else:
                                print("Invalid pulse width. Use values between 500-2500.")
                        except (ValueError, IndexError):
                            print("Invalid pulse value.")
                            
                    else:
                        print("Invalid command format. Use '<channel>.angle <angle>' or '<channel>.init <pulse>'")
                        
            elif " " in cmd:  # Check for channel and pulse format
                parts = cmd.split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    channel = int(parts[0])
                    pulse = int(parts[1])
                    
                    if channel not in servo_channels:
                        print(f"Invalid channel. Use one of: {servo_channels}")
                    elif 500 <= pulse <= 2500:
                        print(f"Setting {servo_names.get(channel, f'Servo {channel}')} to {pulse}µs")
                        servo_dict[channel].set_pulse(pulse)
                    else:
                        print("Invalid pulse width. Use values between 500-2500.")
                else:
                    print("Invalid command format. Use '<channel> <pulse>'")
                    
            elif cmd.isdigit():
                channel = int(cmd)
                if channel in servo_channels:
                    print(f"Centering {servo_names.get(channel, f'Servo {channel}')}")
                    servo_dict[channel].center()
                else:
                    print(f"Invalid channel. Use one of: {servo_channels}")
                    
            else:
                print("Invalid command")
                
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
    finally:
        # Set all servos to their initial positions before exiting
        print("Setting all servos to initial positions...")
        for channel, servo in servo_dict.items():
            servo.set_pulse(servo.initial_pulse)
        sleep(0.5)
        pca.deinit()
        print("Done. All servos returned to initial positions and PCA9685 closed.")

if __name__ == '__main__':
    main()