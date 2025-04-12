from smbus2 import SMBus
from time import sleep
import socket
import json
import time
from enum import Enum

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
    def __init__(self, channel, pca, min_pulse=900, max_pulse=2100, name="unnamed"):
        self.channel = channel
        self.pca = pca
        self.min_pulse = min_pulse
        self.max_pulse = max_pulse
        self.current_pulse = 1500  # Neutral position
        self.name = name
        
    def set_angle(self, angle):
        """Set servo position using angle (0-180°)"""
        # Ensure angle is within bounds
        angle = max(0, min(180, angle))
        # Convert angle to value (-1 to 1)
        value = (angle / 90.0) - 1.0
        # Map value to pulse width
        pulse_width = self._map_value_to_pulse(value)
        self._set_pulse_width(pulse_width)
        
    def _map_value_to_pulse(self, value):
        """Map a value from -1,1 to min_pulse,max_pulse"""
        value = max(-1.0, min(1.0, value))  # Ensure value is in range
        return self.min_pulse + (value + 1) * (self.max_pulse - self.min_pulse) / 2
        
    def _set_pulse_width(self, pulse_width):
        """Set the servo pulse width directly"""
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        print(f"{self.name} (Channel {self.channel}): {pulse_width} µs")
        self.current_pulse = pulse_width
        time.sleep(0.001)  # Small delay to help register changes

class ArmState(Enum):
    """State enum for arm positions"""
    STOWED = 0      # Arm in storage/travel position (X button)
    FULLY_OUT = 1   # Arm fully extended straight out (Y button)
    FULLY_DOWN = 2  # Arm fully down (Right Bumper)
    OUT_DOWN = 3    # Arm out with elbow down (Left Bumper)

class Arm:
    """Main class that controls all arm servos"""
    
    # Default angle presets for each position
    # These can be tuned based on your exact servo positions
    POSITIONS = {
        ArmState.STOWED: {
            "claw": 180,     # Closed position (2100 µs)
            "wrist": 0,      # Horizontal rotation (900 µs)
            "elbow": 10,     # Up position (850 µs)
            "shoulder": 10   # Hidden away (900 µs)
        },
        ArmState.FULLY_OUT: {
            "claw": 0,       # Open position (500 µs)
            "wrist": 90,     # Vertical (1450 µs)
            "elbow": 80,     # Straight out (1250 µs)
            "shoulder": 140  # Extended out (1600 µs)
        },
        ArmState.FULLY_DOWN: {
            "claw": 0,       # Open position (500 µs) 
            "wrist": 90,     # Vertical (1450 µs)
            "elbow": 140,    # Down position (1600 µs)
            "shoulder": 80   # Down position (1125 µs)
        },
        ArmState.OUT_DOWN: {
            "claw": 0,       # Open position (500 µs)
            "wrist": 90,     # Vertical (1450 µs)
            "elbow": 140,    # Down position (1600 µs)
            "shoulder": 140  # Extended out (1600 µs)
        }
    }
    
    def __init__(self, pca):
        """Initialize the arm with all servos"""
        self.pca = pca
        self.current_state = ArmState.STOWED
        
        # Create servo objects with correct channel assignments and names
        self.servos = {
            "claw": Servo(0, pca, min_pulse=500, max_pulse=2100, name="Claw"),
            "wrist": Servo(1, pca, min_pulse=900, max_pulse=2000, name="Wrist"),
            "elbow": Servo(2, pca, min_pulse=850, max_pulse=1600, name="Elbow"),
            "shoulder": Servo(3, pca, min_pulse=900, max_pulse=1600, name="Shoulder")
        }
        
        # Store the current wrist angle for rotation control
        self.current_wrist_angle = 90  # Start at neutral/vertical
        
        # Initialize to stowed position
        self.set_state(ArmState.STOWED)
        
    def set_state(self, state):
        """Set the arm to a predefined state"""
        if state not in ArmState:
            print(f"Invalid state: {state}")
            return False
            
        print(f"Setting arm to {state.name} position...")
        
        # Get the preset positions for this state
        positions = self.POSITIONS[state]
        
        # Set each servo to its position with a small delay between each
        for servo_name, angle in positions.items():
            # Skip wrist adjustment if already at target angle
            if servo_name == "wrist" and abs(self.current_wrist_angle - angle) < 5:
                continue
                
            self.servos[servo_name].set_angle(angle)
            
            # Update current wrist angle if we're adjusting it
            if servo_name == "wrist":
                self.current_wrist_angle = angle
                
            sleep(0.1)  # Small delay between servo movements
            
        self.current_state = state
        print(f"Arm now in {state.name} position")
        return True
        
    def open_claw(self):
        """Open the claw"""
        self.servos["claw"].set_angle(0)  # 0° = open
        print("Claw opened")
        
    def close_claw(self):
        """Close the claw"""
        self.servos["claw"].set_angle(180)  # 180° = closed
        print("Claw closed")
        
    def adjust_wrist(self, direction, step=5):
        """
        Adjust wrist rotation incrementally
        direction: -1 for left, 1 for right
        step: angle change in degrees
        """
        # Calculate new angle based on direction
        new_angle = self.current_wrist_angle + (direction * step)
        new_angle = max(0, min(180, new_angle))  # Ensure within bounds
        
        if new_angle != self.current_wrist_angle:
            self.servos["wrist"].set_angle(new_angle)
            self.current_wrist_angle = new_angle
            print(f"Wrist rotated to {new_angle}°")
        
    def process_controller_input(self, buttons, prev_buttons, hat, prev_hat):
        """Process controller inputs to control the arm"""
        # No inputs, do nothing
        if not buttons or len(buttons) < 12:  # Need enough buttons for A, B, X, Y, LB, RB
            return
            
        # A button (index 0): Open claw
        if buttons[0] == 1:
            self.open_claw()
                
        # B button (index 1): Close claw
        if buttons[1] == 1:
            self.close_claw()
                
        # X button (index 2): Stowed position
        if buttons[2] != prev_buttons[2] and buttons[2] == 1:
            self.set_state(ArmState.STOWED)
                
        # Y button (index 3): Fully out position
        if buttons[3] != prev_buttons[3] and buttons[3] == 1:
            self.set_state(ArmState.FULLY_OUT)
                
        # Right Bumper (index 5): Fully down position
        if len(buttons) > 5 and buttons[5] != prev_buttons[5] and buttons[5] == 1:
            self.set_state(ArmState.FULLY_DOWN)
                
        # Left Bumper (index 4): Out with elbow down position
        if len(buttons) > 4 and buttons[4] != prev_buttons[4] and buttons[4] == 1:
            self.set_state(ArmState.OUT_DOWN)
                
        # D-pad for continuous wrist rotation (hold to rotate)
        if hat and len(hat) > 0:
            if hat[0][0] == -1:  # Left on D-pad
                self.adjust_wrist(-1)  # Rotate left
            elif hat[0][0] == 1:  # Right on D-pad
                self.adjust_wrist(1)   # Rotate right

def main():
    # Initialize the PCA9685 driver
    pca = PCA9685(bus_number=7)
    pca.frequency = 50  # Standard frequency for servos
    
    # Create and initialize arm
    arm = Arm(pca)
    print("Arm initialized to STOWED position.")
    sleep(1)
    
    # Network configuration for controller input
    HOST = '192.168.1.237'  # Update to your IP
    PORT = 4891
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    
    print(f"Server listening on {HOST}:{PORT}...")
    
    prev_buttons = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    prev_hat = [(0, 0)]  # Initialize with neutral position
    
    try:
        while True:
            com_socket, addy = server.accept()
            print(f"Connected to {addy}")
            
            while True:
                data = com_socket.recv(1024)
                if not data:
                    break
                
                raw_data = data.decode('utf-8')
                print(f"Received data: {raw_data}")
                
                try:
                    # Parse controller data
                    json_str = raw_data.replace("'", '"')
                    controller_data = json.loads(json_str)
                    
                    # Get controller inputs
                    buttons = controller_data.get('buttons', [])
                    hat = controller_data.get('hats', [])
                    
                    if buttons or hat:
                        arm.process_controller_input(buttons, prev_buttons, hat, prev_hat)
                        prev_buttons = buttons.copy() if buttons else prev_buttons
                        prev_hat = hat.copy() if hat else prev_hat
                    
                except json.JSONDecodeError as e:
                    print(f"JSON decoding error: {e}")
                    print(f"Problematic JSON data: {raw_data}")
                except Exception as e:
                    print(f"Error processing data: {e}")
            
            com_socket.send("Message received".encode('utf-8'))
            com_socket.close()
            print(f"Connection with {addy} ended.")
            
    except KeyboardInterrupt:
        print("Server is shutting down...")
    finally:
        # Move arm to stowed position before shutdown
        arm.set_state(ArmState.STOWED)
        sleep(1)
        # Close the bus
        pca.deinit()
        server.close()
        print("Server closed and arm stowed.")

if __name__ == '__main__':
    main()