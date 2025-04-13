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
        # Arcade drive called on jetson
        
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
# import json
# import math
# from arcadeDrive import arcadeDrive3  # Import your drive function

# pygame.init()
# pygame.joystick.init()

# # Make sure at least one joystick is connected
# if pygame.joystick.get_count() == 0:
#     raise RuntimeError("No joystick found!")
# joystick = pygame.joystick.Joystick(0)
# joystick.init()


# class ControllerMapper:
#     def __init__(self):
#         # Mapping configuration:
#         # - Axes: keys map to an axis index, with options for inversion and deadzone.
#         # - Triggers: same as axes, but may include a transform function.
#         # - Buttons: each entry maps a logical button name to a specific button index.
#         # - Hats: each entry maps a logical hat name to a specific hat index.
        
#         # left joystick left/right  = axis0
#         # left joystick up/down     = axis1
#         # right joystick left/right = axis2
#         # right joystick up/down    = axis3
#         # left trigger              = axis4
#         # right trigger             = axis5
#         # a                         = button 0
#         # b                         = button 1
#         # x                         = button 2
#         # y                         = button 3
#         # left bumper               = button 4
#         # right bumper              = button 5
#         # back                      = button 6
#         # start                     = button 7
#         # xbox                      = button ? (not used)
#         # dpad up                   = hat0[1] = 1
#         # dpad right                = hat0[0] = 1
#         # dpad down                 = hat0[1] = -1
#         # dpad left                 = hat0[0] = -1
        
        
        
#         self.mapping = {
#             'linear': {
#                 'x': {'axis': 0, 'invert': False, 'deadzone': 0.1},
#                 'y': {'axis': 1, 'invert': True,  'deadzone': 0.1},
#             },
#             'rotation': {
#                 'turnRL': {'axis': 2, 'invert': False, 'deadzone': 0.1},
#                 'ry':   {'axis': 3, 'invert': False, 'deadzone': 0.1},
#             },
#             'triggers': {
#                 'up': {'axis': 5, 'invert': False, 'deadzone': 0.0, 'transform': lambda x: (x + 1) / 2},
#                 'down':  {'axis': 4, 'invert': False, 'deadzone': 0.0, 'transform': lambda x: (x + 1) / 2},
#             },
#             'buttons': {
#                 'openClaw':  {'button': 0},  # A button
#                 'closeClaw': {'button': 1},  # B button
#                 'arm_move':  {'button': 2},  # X button: used to move the arm up/down
#                 'Y': {'button': 3}, # probably rename to 'action1' or something
#                 'LB': {'button': 4},
#                 'RB': {'button': 5},
#                 'Back': {'button': 6},
#                 'Start': {'button': 7},
#                 # Add additional buttons if needed.
#             },
#             'hats': {
#                 'arm_rotate': {'hat': 0, 'component': 'x'}  # This assumes a single hat controlling the d-pad.
#             }
#         }
#         self.previous_state = self._create_empty_state()

#     def _create_empty_state(self):
#         state = {
#             'linear': {'x': 0.0, 'y': 0.0},
#             'rotation': {'theta': 0.0, 'phi': 0.0},
#             'triggers': {'right_Trigger': 0.0, 'left_Trigger': 0.0},
#             'buttons': {},
#             'hats': {},
#             'motor_values': [0, 0, 0, 0],
#             'arm': {'rotate': 0, 'move': 0, 'claw': None}
#         }
        
#         for btn_name in self.mapping.get('buttons', {}):
#             state['buttons'][btn_name] = 0
#         # Initialize hats; here we assume each hat returns a tuple (x, y)
#         for hat_name in self.mapping.get('hats', {}):
#             state['hats'][hat_name] = (0, 0)
#         return state

#     def _apply_deadzone(self, value, deadzone):
#         return 0.0 if abs(value) < deadzone else value

#     def _process_axis(self, config):
#         # Get raw axis value
#         value = joystick.get_axis(config['axis'])
#         # Apply custom transformation if defined
#         if 'transform' in config:
#             value = config['transform'](value)
#         # Invert the value if needed
#         if config.get('invert', False):
#             value = -value
#         # Apply deadzone filtering
#         return self._apply_deadzone(value, config.get('deadzone', 0.0))

#     def get_state(self):
#         state = self._create_empty_state()
        
#         # Process axes
#         for key in ['linear', 'rotation']:
#             for subkey, conf in self.mapping[key].items():
#                 state[key][subkey] = self._process_axis(conf)
#         # Process triggers
#         for trig, conf in self.mapping['triggers'].items():
#             state['triggers'][trig] = self._process_axis(conf)
            
#         # Process buttons
#         for btn_name, conf in self.mapping['buttons'].items():
#             state['buttons'][btn_name] = joystick.get_button(conf['button'])
            
#         # Process hats: for arm_rotate, we only need the x component.
#         for hat_name, conf in self.mapping['hats'].items():
#             hat_value = joystick.get_hat(conf['hat'])
#             # Assuming hat returns a tuple (x, y)
#             state['hats'][hat_name] = hat_value
#             if conf.get('component') == 'x':
#                 state['arm']['rotate'] = hat_value[0]
#             elif conf.get('component') == 'y':
#                 state['arm']['rotate'] = hat_value[1]
#         # Map buttons to arm actions:
#         # - 'openClaw' button => open claw
#         # - 'closeClaw' button => close claw
#         # - 'arm_move' button => arm move (toggle or analog if desired)
#         if state['buttons'].get('openClaw', 0):
#             state['arm']['claw'] = 'open'
#         elif state['buttons'].get('closeClaw', 0):
#             state['arm']['claw'] = 'close'
#         else:
#             state['arm']['claw'] = 'neutral'
#         # For arm move (up/down), we use the X button value.
#         # Here, if the button is pressed, we set a fixed move value (e.g., 1 for up).
#         # You could modify this to support a toggle or incremental move.
#         state['arm']['move'] = state['buttons'].get('arm_move', 0)

#         # Compute motor values using arcadeDrive3 as before.
#         x = state['linear']['x']
#         y = state['linear']['y']
#         rx = state['rotation']['theta']
#         rT = state['triggers']['right_Trigger']
#         lT = state['triggers']['left_Trigger']
#         state['motor_values'] = arcadeDrive3(x, y, rx, rT, lT)

#         # Optionally, print changes compared to previous state.
#         for key in state:
#             if state[key] != self.previous_state.get(key):
#                 print(f"Changed {key}: {state[key]}")
#         self.previous_state = state.copy()
#         return state


# def get_controller_input():
#     mapper = ControllerMapper()
#     while True:
#         pygame.event.pump()  # Process events
#         state = mapper.get_state()
#         yield state


# # Example usage: print state changes
# # if __name__ == '__main__':
# #     for controller_state in get_controller_input():
# #         # You can send this state over a network or use it for further processing.
# #         print(json.dumps(controller_state))
