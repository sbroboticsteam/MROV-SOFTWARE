import pygame
import json
import socket  # For communication with the Raspberry Pi
from arcadeDrive import arcadeDrive3

# Default control mapping (can be customized)
mapping_dict = {
    'left_joy': move_x,
    'right_joy':
    'left_trigger':
    'right_trigger':
    'D-Pad':
    'left_bumper':
    'right_bumper':
    'A': 
    'B':
    'X': 
    'Y':
}

# Define actions
def move_x(value):
    return value

def move_y(value):
    return value

def rotate(value):
    return value

def ascend(value):
    return value

def descend(value):
    return value

# Mapping actions to functions
action_functions = {
    "move_x": move_x,
    "move_y": move_y,
    "rotate": rotate,
    "ascend": ascend,
    "descend": descend,
}

pygame.joystick.init()
joysticks = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]

def get_controller_input():
    pygame.init()
    joystick = pygame.joystick.Joystick(0)

    while True:
        pygame.event.pump()  # Process events
        
        # Read joystick axes and triggers
        x = joystick.get_axis(0)  # Left stick X-axis
        y = -1 * joystick.get_axis(1)  # Left stick Y-axis (inverted)
        rx = joystick.get_axis(2)  # Right stick X-axis
        rT = (joystick.get_axis(5) + 1) / 2.0  # Right trigger (normalized to 0-1)
        lT = (joystick.get_axis(4) + 1) / 2.0  # Left trigger (normalized to 0-1)

        # Apply custom mappings
        actions = {
            "move_x": mapping_dict["left_stick_x"]["scale"] * x,
            "move_y": mapping_dict["left_stick_y"]["scale"] * y,
            "rotate": mapping_dict["right_stick_x"]["scale"] * rx,
            "ascend": mapping_dict["right_trigger"]["scale"] * rT,
            "descend": mapping_dict["left_trigger"]["scale"] * lT,
        }

        # Compute motor values using arcadeDrive3
        motor_values = arcadeDrive3(
            actions["move_x"], actions["move_y"], actions["rotate"],
            actions["ascend"], actions["descend"]
        )

        # Package motor values as JSON
        yield motor_values
