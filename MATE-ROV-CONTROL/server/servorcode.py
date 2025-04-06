import socket
import json
from gpiozero import Servo
<<<<<<< HEAD
from enum import Enum

# Setup your servos (adjust GPIO pins and pulse widths as needed)
servo_armOne = Servo(10, min_pulse_width=0.0005, max_pulse_width=0.0025)
servo_armTwo = Servo(11, min_pulse_width=0.0005, max_pulse_width=0.0025)
servo_claw = Servo(12, min_pulse_width=0.0005, max_pulse_width=0.0025)
=======

# Setup your servos (adjust GPIO pins and pulse widths as needed)
servo_hold = Servo(12, min_pulse_width=0.0005, max_pulse_width=0.0025)
>>>>>>> jetson
servo_rotate = Servo(13, min_pulse_width=0.0005, max_pulse_width=0.0025)

def angle_to_value(angle):
    """Convert an angle (0-180°) to a gpiozero servo value (-1 to 1)."""
    angle = max(0, min(180, angle))
<<<<<<< HEAD
    value = (angle / 90.0) - 1.0
    return max(-1.0, min(1.0, value))

# Define desired angles (in degrees) for actions
ARM_ONE_INIT = 0
ARM_ONE_FWD = 0
ARM_ONE_DWN = 0

ARM_TWO_INIT = 0
ARM_TWO_FWD = 0
ARM_TWO_DWN = 0

ROTATE_INIT = 0
ROTATE_LEFT = 0
ROTATE_MID = 0
ROTATE_RIGHT = 0
ROTATE_FAR = 0

OPEN_ANGLE = 180       # Claw fully open
CLOSE_ANGLE = 90       # Claw closed/neutral
NEUTRAL_ANGLE = 0       # Neutral position

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
    
    """
    while:
        process_input(buttons, hats)
    """

class ArmStateMachine:
    
    #add setters for the states
    
    def __init__(self):
        # Start in the idle state
        self.clawState = ClawState.IDLE
        self.rotateState = RotateState.INIT
        self.armState = ArmState.INIT
        


    def process_input(self, buttons, prevButtons, hats, prevHats):
        """
        Update the state based on button inputs.
        Priority order:
          - A button (index 0): Open claw
          - B button (index 1): Close claw
          - X button (index 2): Rotate left
          - Y button (index 3): Rotate right
          - Otherwise, return to idle.
        """
        if len(buttons) < 4:
            # Not enough button data; default to idle
            self.clawState = ClawState.IDLE
            self.rotateState = RotateState.INIT
            self.armState = ArmState.INIT
            return

        # Arm States
        if self.armState == ArmState.INIT:
            servo_armOne.value = angle_to_value(ARM_ONE_INIT)
            servo_armTwo.value = angle_to_value(ARM_TWO_INIT)
            
            if buttons[2] != prevButtons and buttons[2]:
                self.armState = ArmState.FWD
            
        elif self.armState == ArmState.FWD:
            servo_armOne.value = angle_to_value(ARM_ONE_FWD)
            servo_armTwo.value = angle_to_value(ARM_TWO_FWD)
            
            if buttons[2] != prevButtons and buttons[2]:
                self.armState = ArmState.DWN
                
        elif self.armState == ArmState.DWN:
            servo_armOne.value = angle_to_value(ARM_ONE_DWN)
            servo_armTwo.value = angle_to_value(ARM_TWO_DWN)
            
            if buttons[2] != prevButtons and buttons[2]:
                self.armState = ArmState.FWD
                
        elif self.armState == ArmState.MAN:
            return
            
        #Wrist State Machine
        if self.rotateState == RotateState.INIT:
            servo_rotate.value = angle_to_value(ROTATE_INIT)
            
            if buttons[2] != prevButtons and buttons[2]:
                self.armState = ArmState.FWD

        elif self.rotateState == RotateState.ROTATE_LEFT:
            servo_rotate.value = angle_to_value(ROTATE_LEFT)
            
            if hats[0][0] != prevHats[0][0] and hats[0][0] == 1: 
                self.rotateState = RotateState.ROTATE_MID
        
        elif self.rotateState == RotateState.ROTATE_MID:
            servo_rotate.value = angle_to_value(ROTATE_MID)
            
            if hats[0][0] != prevHats[0][0] and hats[0][0] == -1:
                self.rotateState = RotateState.ROTATE_LEFT
            if hats[0][0] != prevHats[0][0] and hats[0][0] == 1:  
                self.rotateState = RotateState.ROTATE_RIGHT
     
        elif self.rotateState == RotateState.ROTATE_RIGHT:
            servo_rotate.value = angle_to_value(ROTATE_RIGHT)
            
            if hats[0][0] != prevHats[0][0] and hats[0][0] == -1: 
                self.rotateState = RotateState.ROTATE_MID
            if hats[0][0] != prevHats[0][0] and hats[0][0] == 1: 
                self.rotateState = RotateState.ROTATE_FAR
       
        elif self.rotateState == RotateState.ROTATE_FAR:
            servo_rotate.value = angle_to_value(ROTATE_FAR)
            
            if hats[0][0] != prevHats[0][0] and hats[0][0] == -1:  
                self.rotateState = RotateState.ROTATE_RIGHT
        
        
        if len(buttons) > 0 and buttons[0] == 1:  # A Button
            servo_claw.value = angle_to_value(OPEN_ANGLE)
            print("A Pressed → Open Claw")
        elif len(buttons) > 1 and buttons[1] == 1:  # B Button
            servo_claw.value = angle_to_value(CLOSE_ANGLE)
            print("B Pressed → Close Claw")
        else:
            servo_claw.value = angle_to_value(NEUTRAL_ANGLE)  

# Network configuration
=======

    # Map 0–180 → -1.0 to 1.0
    value = (angle / 90.0) - 1.0

    # Extra clamp to handle rounding errors
    return max(-1.0, min(1.0, value))

# Define desired angles for your actions (in degrees)
OPEN_ANGLE = 180       # Claw fully open
CLOSE_ANGLE = 90       # Claw closed/neutral
LEFT_ROTATE_ANGLE = 180  # Rotate hand fully left (0°)
RIGHT_ROTATE_ANGLE = 90  # Rotate hand fully right (180°)
NEUTRAL_ANGLE = 0     # Neutral for rotation

>>>>>>> jetson
HOST = '192.168.1.133'
PORT = 4891

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(5)
<<<<<<< HEAD
print(f"Server listening on {HOST}:{PORT}...")

# Instantiate the arm state machine
arm_sm = ArmStateMachine()
prevButtons = [0,0,0,0,0,0,0,0,0,0,0,0,0]
prevHats = #[soemthing that the hats are int]
=======

print(f"Server listening on {HOST}:{PORT}...")
>>>>>>> jetson

try:
    while True:
        com_socket, addy = server.accept()
        print(f"Connected to {addy}")
        while True:
            data = com_socket.recv(1024)
            if not data:
                break

            raw_data = data.decode('utf-8')
            print(f"Raw Received Data: {raw_data}")
<<<<<<< HEAD
            try:
                # Convert single quotes to double quotes for valid JSON
                json_str = raw_data.replace("'", '"')
                controller_inputs = json.loads(json_str)
                print(f"Parsed Controller Inputs: {controller_inputs}")
                
                # Retrieve button data (assumes at least 4 buttons)
                buttons = controller_inputs.get('buttons', [])
                hats = controller_inputs.get('hats', [])
                arm_sm.process_input(buttons, prevButtons, hats, prevHats)
                prevButtons = buttons
                prevHats = hats

=======

            try:
                # Convert single quotes to double quotes to form valid JSON.
                json_compatible_string = raw_data.replace("'", '"')
                controller_inputs = json.loads(json_compatible_string)
                print(f"Parsed Controller Inputs: {controller_inputs}")

                # Process button data for servos:
                # Assume controller_inputs has a key "buttons" which is a list of at least 4 values.
                buttons = controller_inputs.get('buttons', [])

                # Hand Control: servo_hold
                # A (Button 0) opens the hand; B (Button 1) closes the hand.
                # ----- Claw (servo_hold) -----
                if len(buttons) > 0 and buttons[0] == 1:  # A Button
                    servo_hold.value = angle_to_value(OPEN_ANGLE)
                    print("A Pressed → Open Claw")
                elif len(buttons) > 1 and buttons[1] == 1:  # B Button
                    servo_hold.value = angle_to_value(CLOSE_ANGLE)
                    print("B Pressed → Close Claw")
                else:
                    servo_hold.value = angle_to_value(NEUTRAL_ANGLE)  # Default to closed

                # ----- Rotation (servo_rotate) -----
                if len(buttons) > 2 and buttons[2] == 1:  # X Button
                    servo_rotate.value = angle_to_value(OPEN_ANGLE)
                    print("X Pressed → Rotate Left")
                elif len(buttons) > 3 and buttons[3] == 1:  # Y Button
                    servo_rotate.value = angle_to_value(CLOSE_ANGLE)
                    print("Y Pressed → Rotate Right")
                else:
                    servo_rotate.value = angle_to_value(NEUTRAL_ANGLE)  # Default neutral

                
>>>>>>> jetson
            except json.JSONDecodeError as e:
                print(f"JSON decoding error: {e}")
                print(f"Problematic JSON data: {raw_data}")

        com_socket.send("Message received".encode('utf-8'))
        com_socket.close()
<<<<<<< HEAD
        print("Connection ended. Waiting for next connection...\n")
=======
        print(f"Connection with {addy} ended.")
>>>>>>> jetson

except KeyboardInterrupt:
    print("Server is shutting down...")

finally:
    server.close()
