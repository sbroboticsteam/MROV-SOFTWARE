import pygame
import math
from arcadeDrive import arcadeDrive, arcadeDrive2, arcadeDrive3

pygame.joystick.init()
joysticks = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]

for joystick in joysticks:
    joystick.init()


def get_controller_input():
    pygame.init()
    joystick = joysticks[0]
    
    previous_state = {
        "axes": {"left_stick": {"x": 0, "y": 0}, "right_stick": {"x": 0, "y": 0}},
        "motor_values": [0, 0, 0, 0],
        "buttons": [0 for _ in range(joystick.get_numbuttons())],
        "hats": [0 for _ in range(joystick.get_numhats())],
        "triggers": {"left_Trigger": [-1.0], "right_Trigger": [-1.0]},
    }
    
    while True:
        pygame.event.pump()  # Process events
        x = joystick.get_axis(0)  # X-axis
        y = -1 * (joystick.get_axis(1))  # Y-axis
        ry = joystick.get_axis(3)
        rx = joystick.get_axis(2)
        rT = joystick.get_axis(5)
        rT = (rT+1)/2.0
        lT = joystick.get_axis(4)
        lT = (lT+1)/2.0
        
        buttons = [joystick.get_button(i) for i in range(joystick.get_numbuttons())]
        hats = [joystick.get_hat(i) for i in range(joystick.get_numhats())]
        # motor_values = arcadeDrive3(x, y, rx)
        motor_values = arcadeDrive3(x, y, rx, rT, lT)
        
        inputs = {
            "axes": {"left_stick": {"x": x, "y": y}, "right_stick": {"x": rx, "y": ry}},
            "motor_values": motor_values,
            "buttons": buttons,
            "hats": hats,
            "triggers": {"left_Trigger": [lT], "right_Trigger": [rT]},
        }
        
        for key in inputs:
            if key == "axes":  # Compare axes separately
                for stick, values in inputs[key].items():
                    for axis, value in values.items():
                        if value != previous_state[key][stick][axis]:
                            print(f"Changed {stick} {axis}: {value}")
            elif key == "buttons":  # Compare buttons separately
                for i, value in enumerate(inputs[key]):
                    if value != previous_state[key][i]:
                        print(f"Changed button {i}: {value}")
            elif key == "hats":  # Compare hats separately
                for i, value in enumerate(inputs[key]):
                    if value != previous_state[key][i]:
                        print(f"Changed hat {i}: {value}")
            else:  # Compare other keys directly
                if inputs[key] != previous_state[key]:
                    print(f"Changed {key}: {inputs[key]}")

        # Update the previous state
        previous_state = inputs.copy()
        
        yield inputs

# import pygame
# import math
# from arcadeDrive import arcadeDrive, arcadeDrive2, arcadeDrive3

# class ControllerMapper:
#     def __init__(self):
#         pygame.init()
#         pygame.joystick.init()
        
#         # Initialize controller
#         if pygame.joystick.get_count() == 0:
#             raise RuntimeError("No controller found!")
#         self.joystick = pygame.joystick.Joystick(0)
#         self.joystick.init()

#         # Customizable mapping configuration
#         self.mapping = {
#             'linear': {
#                 'x': {'axis': 0, 'invert': False, 'deadzone': 0.1},
#                 'y': {'axis': 1, 'invert': True, 'deadzone': 0.1},
#                 'z': {'axis': 5, 'transform': lambda x: (x + 1) / 2}  # Right trigger
#             },
#             'rotation': {
#                 'theta': {'axis': 2, 'deadzone': 0.1},  # Right stick X
#                 'phi': {'axis': 3, 'deadzone': 0.1},    # Right stick Y
#                 'rho': {'axis': 4, 'transform': lambda x: (x + 1) / 2}  # Left trigger
#             },
#             'arm': {
#                 'position': {'buttons': [4, 5]},  # LB/RB buttons
#                 'claw': {'buttons': [0, 1]}       # A/B buttons
#             }
#         }

#         # Initialize state
#         self.previous_state = self._create_empty_state()

#     def _create_empty_state(self):
#         return {
#             'axes': {
#                 'left_stick': {'x': 0.0, 'y': 0.0},
#                 'right_stick': {'x': 0.0, 'y': 0.0}
#             },
#             'triggers': {
#                 'left_Trigger': 0.0,
#                 'right_Trigger': 0.0
#             },
#             'buttons': {},
#             'motor_values': [0, 0, 0, 0]
#         }

#     def _apply_deadzone(self, value, deadzone):
#         return 0.0 if abs(value) < deadzone else value

#     def _process_axis(self, config):
#         raw = self.joystick.get_axis(config['axis'])
        
#         # Apply transformations
#         if 'transform' in config:
#             raw = config['transform'](raw)
            
#         # Apply inversion
#         if config.get('invert', False):
#             raw = -raw
            
#         # Apply deadzone
#         return self._apply_deadzone(raw, config.get('deadzone', 0.0))

#     def get_controller_input(self):
#         pygame.event.pump()
#         new_state = self._create_empty_state()

#         # Process linear controls
#         new_state['axes']['left_stick']['x'] = self._process_axis(
#             self.mapping['linear']['x']
#         )
#         new_state['axes']['left_stick']['y'] = self._process_axis(
#             self.mapping['linear']['y']
#         )
#         new_state['triggers']['right_Trigger'] = self._process_axis(
#             self.mapping['linear']['z']
#         )

#         # Process rotational controls
#         new_state['axes']['right_stick']['x'] = self._process_axis(
#             self.mapping['rotation']['theta']
#         )
#         new_state['triggers']['left_Trigger'] = self._process_axis(
#             self.mapping['rotation']['rho']
#         )

#         # Generate motor values
#         new_state['motor_values'] = arcadeDrive3(
#             new_state['axes']['left_stick']['x'],
#             new_state['axes']['left_stick']['y'],
#             new_state['axes']['right_stick']['x'],
#             new_state['triggers']['right_Trigger'],
#             new_state['triggers']['left_Trigger']
#         )

#         # Detect changes
#         for key in new_state:
#             if new_state[key] != self.previous_state[key]:
#                 print(f"Changed {key}: {new_state[key]}")

#         self.previous_state = new_state.copy()
#         return new_state

# class RobotController:
#     def __init__(self):
#         self.mapper = ControllerMapper()
        
#     def run(self):
#         try:
#             while True:
#                 # Get mapped controller state
#                 state = self.mapper.get_state()
                
#                 # Convert to motor commands using existing arcadeDrive
#                 motor_values = self._convert_to_motor_commands(state)
                
#                 # Send to motors (replace with your actual implementation)
#                 self._send_to_motors(motor_values)
                
#         except KeyboardInterrupt:
#             print("\nStopping controller...")
#             pygame.quit()

#     def _convert_to_motor_commands(self, state):
#         """Convert mapped state to arcadeDrive3 parameters"""
#         # Extract values using our mapping
#         x = state['linear']['x']
#         y = state['linear']['y']
#         rx = state['rotation']['theta']
#         rT = state['linear']['z']   # Right trigger mapped to z
#         lT = state['rotation']['rho']  # Left trigger mapped to rho
        
#         return arcadeDrive3(x, y, rx, rT, lT)

#     def _send_to_motors(self, motor_values):
#         """Replace this with your actual motor control logic"""
#         print(f"Motor commands: {motor_values}")
#         # Example: ser.write(motor_values) for serial communication

# if __name__ == "__main__":
#     controller = RobotController()
#     controller.run()
