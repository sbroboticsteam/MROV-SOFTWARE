import inputs
import math
from collections import defaultdict

class XboxController:
    def __init__(self):
        self.gamepad = inputs.devices.gamepads[0]
        self.deadzone = 0.1  # Adjust deadzone as needed
        
        # Define your controller mapping here
        self.mapping = {
            # Analog controls (axes)
            'ABS_X': 'x',          # Left stick X
            'ABS_Y': 'y',          # Left stick Y
            'ABS_RX': 'theta',     # Right stick X
            'ABS_RY': 'phi',       # Right stick Y
            'ABS_Z': 'rho',        # Left trigger
            'ABS_RZ': 'z',         # Right trigger
            
            # Buttons
            'BTN_SOUTH': 'openClaw',   # A button
            'BTN_EAST': 'closeClaw',   # B button
            'BTN_WEST': 'armUp',       # X button
            'BTN_NORTH': 'armDown'     # Y button
            #BTN_TL
            #BTN_THUMBR
            #ABS_HAT0X
            #ABS_HAT0Y
            #BTN_START
            #BTN_SELECT
        }
        
        # Initialize state with default values
        self.state = defaultdict(float)
        self.state.update({
            'x': 0.0, 'y': 0.0, 'z': 0.0,
            'theta': 0.0, 'phi': 0.0, 'rho': 0.0,
            'openClaw': 0, 'closeClaw': 0,
            'armUp': 0, 'armDown': 0
        })

    def normalize_axis(self, value):
        """Normalize axis values to [-1.0, 1.0] range with deadzone"""
        normalized = value / 32768.0
        if abs(normalized) < self.deadzone:
            return 0.0
        return normalized

    def normalize_trigger(self, value):
        """Normalize trigger values to [0.0, 1.0] range"""
        return value / 255.0

    def read_inputs(self):
        """Read and process controller events"""
        events = inputs.get_gamepad()
        for event in events:
            if event.ev_type == 'Sync':
                continue
                
            if event.code in self.mapping:
                control = self.mapping[event.code]
                
                # Handle different event types
                if event.ev_type == 'Absolute':
                    if event.code in ['ABS_Z', 'ABS_RZ']:  # Triggers
                        self.state[control] = self.normalize_trigger(event.state)
                    else:  # Sticks
                        self.state[control] = self.normalize_axis(event.state)
                
                elif event.ev_type == 'Key':  # Buttons
                    self.state[control] = event.state

        return self.state

class RobotController:
    def __init__(self):
        self.xbox = XboxController()
        
    def run(self):
        try:
            while True:
                # Get current controller state
                controls = self.xbox.read_inputs()
                
                # Process controls
                motion_data = {
                    'linear': [controls['x'], controls['y'], controls['z']],
                    'rotation': [controls['theta'], controls['phi'], controls['rho']],
                    'arm': {
                        'position': controls['armUp'] - controls['armDown'],
                        'claw': controls['openClaw'] - controls['closeClaw']
                    }
                }
                
                # Call your existing motor control function here
                self.send_to_motors(motion_data)
                
        except KeyboardInterrupt:
            print("Stopping robot control")

    def send_to_motors(self, motion_data):
        """Replace this with your actual motor control function"""
        # Example: call your existing kinematics function
        # motor_commands = your_kinematics_function(motion_data)
        print(f"Current motion data: {motion_data}")

if __name__ == "__main__":
    controller = RobotController()
    controller.run()