from smbus2 import SMBus
from time import sleep
import socket
import json
import time
import select
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

# Servo class that uses PCA9685 instead of gpiozero
class Servo:
    def __init__(self, channel, pca, min_pulse=1000, max_pulse=2000):
        self.channel = channel
        self.pca = pca
        self.MIN_PULSE = min_pulse
        self.MAX_PULSE = max_pulse
        self.current_pulse = 1500  # Neutral position
        
    def initialize(self):
        # Set to neutral position
        self._set_pulse_width(1500)
        sleep(0.5)
        print(f"Servo on channel {self.channel} initialized")
        
    def set_value(self, value):
        # Value is expected to be between -1 and 1 (like gpiozero)
        pulse_width = self._map_value_to_pulse(value)
        self._set_pulse_width(pulse_width)
        
    def _map_value_to_pulse(self, value):
        # Map value from -1,1 to pulse width
        value = max(-1.0, min(1.0, value))  # Ensure value is in range
        # Linear interpolation from -1,1 to min_pulse,max_pulse
        return self.MIN_PULSE + (value + 1) * (self.MAX_PULSE - self.MIN_PULSE) / 2
        
    def _set_pulse_width(self, pulse_width):
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        print(f"Channel {self.channel}: pulse {pulse_width} µs -> duty_cycle {duty_cycle}")
        self.current_pulse = pulse_width
        time.sleep(0.001)  # Small delay to help register changes

# Define states for the arm using an enumeration
class ClawState(Enum):
    IDLE = 0
    CLAW_OPEN = 1
    CLAW_CLOSED = 2
    
class RotateState(Enum):
    INIT = 0
    ROTATE_LEFT = 1
    ROTATE_MID = 2
    ROTATE_RIGHT = 3
    ROTATE_FAR = 4
    
class ArmState(Enum):
    INIT = 0
    FWD = 1
    DWN = 2
    MAN = 3

def angle_to_value(angle):
    """Convert an angle (0-180°) to a servo value (-1 to 1)."""
    angle = max(0, min(180, angle))
    value = (angle / 90.0) - 1.0
    return max(-1.0, min(1.0, value))

# Modify the angle constants based on your provided values
# Convert pulse width to angles (approximately)

# Claw (channel 0)
CLAW_OPEN = 0      # 500 µs (rest position)
CLAW_CLOSED = 180  # 2100 µs (fully closed)
CLAW_NEUTRAL = 90  # Midpoint position

# Rotate (channel 1)
ROTATE_INIT = 90   # ~1450 µs (vertical position)
ROTATE_LEFT = 45   # More to the left
ROTATE_MID = 90    # Vertical
ROTATE_RIGHT = 135 # More to the right
ROTATE_FAR = 180   # Furthest right (~2000 µs)

# Arm Two (channel 2)
ARM_TWO_INIT = 80  # ~1250 µs (straight out position)
ARM_TWO_UP = 10    # 850 µs (max up)
ARM_TWO_FWD = 80   # 1250 µs (straight out)
ARM_TWO_DWN = 140  # ~1600 µs (down position)

# Arm One (channel 3)
ARM_ONE_INIT = 80  # ~1125 µs (straight down)
ARM_ONE_HIDDEN = 10 # 900 µs (hidden away)
ARM_ONE_FWD = 140  # ~1600 µs (straight out)
ARM_ONE_DWN = 80   # 1125 µs (straight down)

class ArmStateMachine:
    def __init__(self, servos):
        # Start in the idle state
        self.clawState = ClawState.IDLE
        self.rotateState = RotateState.INIT
        self.armState = ArmState.INIT
        
        # Store references to servo objects with their actual functions
        # Note: The keys still match the dictionary keys, but we're mentally remapping
        self.servo_claw = servos["armOne"]     # Channel 0 - Claw
        self.servo_rotate = servos["armTwo"]   # Channel 1 - Rotate
        self.servo_armTwo = servos["claw"]     # Channel 2 - Arm Two
        self.servo_armOne = servos["rotate"]   # Channel 3 - Arm One
    
    def process_input(self, buttons, prevButtons, hats, prevHats):
        """
        Update the state based on button inputs.
        """
        if not buttons or len(buttons) < 4:
            # Not enough button data; default to idle
            self.clawState = ClawState.IDLE
            self.rotateState = RotateState.INIT
            self.armState = ArmState.INIT
            return

        # Arm States
        if self.armState == ArmState.INIT:
            self.servo_armOne.set_value(angle_to_value(ARM_ONE_INIT))
            self.servo_armTwo.set_value(angle_to_value(ARM_TWO_INIT))
            
            if buttons[2] != prevButtons[2] and buttons[2]:
                self.armState = ArmState.FWD
            
        elif self.armState == ArmState.FWD:
            self.servo_armOne.set_value(angle_to_value(ARM_ONE_FWD))
            self.servo_armTwo.set_value(angle_to_value(ARM_TWO_FWD))
            
            if buttons[2] != prevButtons[2] and buttons[2]:
                self.armState = ArmState.DWN
                
        elif self.armState == ArmState.DWN:
            self.servo_armOne.set_value(angle_to_value(ARM_ONE_DWN))
            self.servo_armTwo.set_value(angle_to_value(ARM_TWO_DWN))
            
            if buttons[2] != prevButtons[2] and buttons[2]:
                self.armState = ArmState.FWD
                
        elif self.armState == ArmState.MAN:
            return
            
        # Wrist State Machine
        if self.rotateState == RotateState.INIT:
            self.servo_rotate.set_value(angle_to_value(ROTATE_INIT))
    
            if hats and prevHats and hats[0][0] != prevHats[0][0]:
                if hats[0][0] == -1:
                    self.rotateState = RotateState.ROTATE_LEFT
                elif hats[0][0] == 1:
                    self.rotateState = RotateState.ROTATE_RIGHT

        elif self.rotateState == RotateState.ROTATE_LEFT:
            self.servo_rotate.set_value(angle_to_value(ROTATE_LEFT))
            
            if hats and prevHats and hats[0][0] != prevHats[0][0] and hats[0][0] == 1: 
                self.rotateState = RotateState.ROTATE_MID
        
        elif self.rotateState == RotateState.ROTATE_MID:
            self.servo_rotate.set_value(angle_to_value(ROTATE_MID))
            
            if hats and prevHats and hats[0][0] != prevHats[0][0] and hats[0][0] == -1:
                self.rotateState = RotateState.ROTATE_LEFT
            if hats and prevHats and hats[0][0] != prevHats[0][0] and hats[0][0] == 1:  
                self.rotateState = RotateState.ROTATE_RIGHT
     
        elif self.rotateState == RotateState.ROTATE_RIGHT:
            self.servo_rotate.set_value(angle_to_value(ROTATE_RIGHT))
            
            if hats and prevHats and hats[0][0] != prevHats[0][0] and hats[0][0] == -1: 
                self.rotateState = RotateState.ROTATE_MID
            if hats and prevHats and hats[0][0] != prevHats[0][0] and hats[0][0] == 1: 
                self.rotateState = RotateState.ROTATE_FAR
       
        elif self.rotateState == RotateState.ROTATE_FAR:
            self.servo_rotate.set_value(angle_to_value(ROTATE_FAR))
            
            if hats and prevHats and hats[0][0] != prevHats[0][0] and hats[0][0] == -1:  
                self.rotateState = RotateState.ROTATE_RIGHT
        
        # Claw control
        if buttons[0] != prevButtons[0] and buttons[0] == 1:
            self.clawState = ClawState.CLAW_OPEN
        elif buttons[1] != prevButtons[1] and buttons[1] == 1:
            self.clawState = ClawState.CLAW_CLOSED

        # Act on state
        if self.clawState == ClawState.CLAW_OPEN:
            self.servo_claw.set_value(angle_to_value(CLAW_OPEN))
        elif self.clawState == ClawState.CLAW_CLOSED:
            self.servo_claw.set_value(angle_to_value(CLAW_CLOSED))
        else:
            self.servo_claw.set_value(angle_to_value(CLAW_NEUTRAL))


def main():
    # Initialize the PCA9685 driver
    pca = PCA9685(bus_number=7)
    pca.frequency = 50  # Standard frequency for servos and ESCs
    
    # Initialize ESC controller (for motors)
    # esc_channels = [0, 1, 2, 3, 4, 5, 6, 7]
    # esc_controller = ESCController(esc_channels, pca)
    # esc_controller.initialize_all()
    
    # Initialize servos (using higher channel numbers to avoid conflict with ESCs)
    servos = {
        "armOne": Servo(3, pca, min_pulse=900, max_pulse=2100),
        "armTwo": Servo(2, pca, min_pulse=900, max_pulse=2100),
        "claw": Servo(0, pca, min_pulse=900, max_pulse=2100),
        "rotate": Servo(1, pca, min_pulse=900, max_pulse=2100)
    }
    
    # Initialize all servos
    print("Initializing servos to default positions...")
    
    # Set default positions
    servos["armOne"].set_value(angle_to_value(ARM_ONE_INIT))     # Claw open/rest
    sleep(0.5)
    servos["armTwo"].set_value(angle_to_value(ARM_TWO_INIT))   # Rotate to vertical
    sleep(0.5)
    servos["claw"].set_value(angle_to_value(CLAW_OPEN))    # Arm2 straight out
    sleep(0.5)
    servos["rotate"].set_value(angle_to_value(ROTATE_INIT))  # Arm1 straight down
    sleep(1.0)
    
    print("All servos initialized to default positions")
    
    # Initialize arm state machine
    arm_sm = ArmStateMachine(servos)
    
    # Network configuration
    HOST = '192.168.1.237'  # Change to your IP
    PORT = 4891
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    
    print(f"Server listening on {HOST}:{PORT}...")
    
    prevButtons = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    prevHats = [(0, 0)]  # Initialize with neutral position
    
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
                    # Convert single quotes to double quotes for valid JSON
                    json_str = raw_data.replace("'", '"')
                    controller_data = json.loads(json_str)
                    
                    # Check if we have motor values to update
                    # if 'motor_values' in controller_data:
                    #     motor_states = controller_data['motor_values']
                    #     if isinstance(motor_states, list) and len(motor_states) == 8:
                    #         esc_controller.set_all_states(motor_states)
                    #         print("Motors updated")
                    #     else:
                    #         print("Invalid motor values format")
                    
                    # Check if we have controller inputs for the arm
                    buttons = controller_data.get('buttons', [])
                    hats = controller_data.get('hats', [])
                    
                    if buttons or hats:
                        arm_sm.process_input(buttons, prevButtons, hats, prevHats)
                        prevButtons = buttons.copy() if buttons else prevButtons
                        prevHats = hats.copy() if hats else prevHats
                    
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
        # Ensure the motors are stopped and bus is closed
        esc_controller.stop_all()
        pca.deinit()
        server.close()
        print("Server closed and motors stopped.")

if __name__ == '__main__':
    main()