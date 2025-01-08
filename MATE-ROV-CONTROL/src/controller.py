import pygame
import math
from arcadeDrive import arcadeDrive, arcadeDrive2, arcadeDrive3, arcadeDrive4

mapping_dict = {
    "UP":
        "DOWN"
}

pygame.joystick.init()
joysticks = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]

def get_controller_input():
    pygame.init()
    joystick = pygame.joystick.Joystick(0)
    
    previous_state = {
        "axes": {"left_stick": {"x": 0, "y": 0}, "right_stick": {"x": 0, "y": 0}},
        "motor_values": [0, 0, 0, 0],
        "buttons": {f"button_{i}": 0 for i in range(joystick.get_numbuttons())},
        "hats": [0 for _ in range(joystick.get_numhats())],
        "triggers": {"left_Trigger": {-1.0}, "right_Trigger": {-1.0}},
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
        
        buttons = {f"button_{i}": joystick.get_button(i) for i in range(joystick.get_numbuttons())}
        hats = [joystick.get_hat(i) for i in range(joystick.get_numhats())]
        # motor_values = arcadeDrive3(x, y, rx)
        motor_values = arcadeDrive3(x, y, rx, rT, lT)
        
        inputs = {
            "axes": {"left_stick": {"x": x, "y": y}, "right_stick": {"x": rx, "y": ry}},
            "motor_values": motor_values,
            # "buttons": buttons,
            # "hats": hats,
            # "triggers": {"left_Trigger": {lT}, "right_Trigger": {rT}},
        }
        
        for key in inputs:
            if key == "axes":  # Compare axes separately
                for stick, values in inputs[key].items():
                    for axis, value in values.items():
                        if value != previous_state[key][stick][axis]:
                            print(f"Changed {stick} {axis}: {value}")
            elif key == "buttons":  # Compare buttons separately
                for button, value in inputs[key].items():
                    if value != previous_state[key][button]:
                        print(f"Changed {button}: {value}")
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


