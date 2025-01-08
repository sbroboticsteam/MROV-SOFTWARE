import pygame
import math

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from arcadeDrive import arcadeDrive, arcadeDrive2, arcadeDrive3

pygame.joystick.init()
joysticks = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]


class Player(object):

    def __init__(self):
        self.player = pygame.rect.Rect((300, 400, 50, 50))
        self.color = "white"

    def move(self, x, y):
        self.player.move_ip((1.1 * x, 1.1* y))

    def change_color(self, color):
        self.color = color

    def draw(self, game_screen):
        pygame.draw.rect(game_screen, self.color, self.player)
        
def drawSim(x,y, rx, rT, lT):
    inputs = arcadeDrive3(x, y, rx, rT, lT)
    motor_values = [
        inputs[0],  # Front-Right Motor
        -inputs[1],  # Back-Right Motor
        -inputs[2],  # Back-Left Motor
        inputs[3]   # Front-Left Motor
    ]
    
    width = 800
    height = 600
    center = pygame.Vector2(width / 2, height / 2)
    
    motor_positions = [
        pygame.Vector2(50, -50),  # Front-Right
        pygame.Vector2(50, 50),   # Back-Right
        pygame.Vector2(-50, 50),  # Back-Left
        pygame.Vector2(-50, -50)  # Front-Left
    ]
    
    motor_orientations = [
        -45,  # Front-Right → Backward Right
        45,   # Back-Right → Forward Right
        -45,  
        45    
    ]
    
    motor_colors = ["red", "blue", "green", "yellow"]
    
    pygame.draw.rect(screen, "white", (center.x - 60, center.y - 60, 120, 120), 2)
    pygame.draw.circle(screen, "gray", center, 5)

    for i, motor in enumerate(motor_positions):
        motor_pos = center + motor
        motor_output = motor_values[i] * 50  # Scale motor output
        end_pos = motor_pos + pygame.Vector2(0, motor_output).rotate(motor_orientations[i])
        
        pygame.draw.line(screen, motor_colors[i], motor_pos, end_pos, 5)
        pygame.draw.circle(screen, motor_colors[i], motor_pos, 8)

def get_controller_input():
    pygame.init()
    joystick = pygame.joystick.Joystick(0)
    
    previous_state = {
        "axes": {"left_stick": {"x": 0, "y": 0}, "right_stick": {"x": 0, "y": 0}},
        "motor_values": [0, 0, 0, 0,0, 0, 0, 0],
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
        motor_values = arcadeDrive3(x, y, rx, lT, rT)
        
        inputs = {
            "axes": {"left_stick": {"x": x, "y": y}, "right_stick": {"x": rx, "y": ry}},
            "motor_values": motor_values,
            "buttons": buttons,
            "hats": hats,
            "triggers": {"left_Trigger": {lT}, "right_Trigger": {rT}},
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

player = Player()
clock = pygame.time.Clock()
screen = pygame.display.set_mode((800, 600))
running = True

controller_gen = get_controller_input()

# controller input
while running or KeyboardInterrupt:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
            pygame.quit()
            break
        
    controller_inputs = next(controller_gen)
    left_stick = controller_inputs['axes']['left_stick']
    right_stick = controller_inputs['axes']['right_stick']
    lT = controller_inputs['triggers']['left_Trigger']
    rT = controller_inputs['triggers']['right_Trigger']
    buttons = controller_inputs['buttons']
    hats = controller_inputs['hats']

    screen.fill((0, 0, 0))
    player.draw(screen)
    drawSim(left_stick['x'], left_stick['y'], right_stick['x'], rT, lT)
    pygame.display.update()

    clock.tick(180)


# print(joysticks)

#         if event.type == pygame.JOYAXISMOTION:            
#             y = -1 * (pygame.joystick.Joystick(0).get_axis(1))
#             x = pygame.joystick.Joystick(0).get_axis(0)
            
#             # Check and print the direction based on the axis values

#             # if x < -threshold:  # Left movement
#             #     print(f"LEFT JOY Moving Left: {math.trunc(x* 100) / 100}")
#             # elif x > threshold:  # Right movement
#             #     print(f"LEFT JOY Moving Right: {math.trunc(x* 100) / 100}")
            
#             # if y < -threshold:  # Up movement
#             #     print(f"LEFT JOY Moving Up: {math.trunc(y* 100) / 100}")
#             # elif y > threshold:  # Down movement
#             #     print(f"LEFT JOY Moving Down: {math.trunc(y* 100) / 100}")

#             # print("Y", math.trunc(x* 100) / 100)
#             # print("X", math.trunc(y* 100) / 100)

#         # Following is right stick controls
#         if event.type == pygame.JOYAXISMOTION:
#             ry = pygame.joystick.Joystick(0).get_axis(3)
#             rx = pygame.joystick.Joystick(0).get_axis(2)
            
#             rT = pygame.joystick.Joystick(0).get_axis(5)
#             lT = pygame.joystick.Joystick(0).get_axis(4)
#             rT = (rT+1)/2.0
#             lT = (lT+1)/2.0
#             print(rT)
#             # print(lT)

#             if (rx) > 0.05:
#                  # print(event)
#                  print ("RIGHT JOY Moved right :", (math.trunc(rx * 100)/100))
#             elif (rx) < -0.05:
#                 # print(event)
#                  print("RIGHT JOY Moved left :", (math.trunc(rx * 100)/100))
#             if (ry) > 0.05:  # Issue calculating y axis
#                 # print(event)
#               print ("RIGHT JOY Moved Down :", (math.trunc(ry * 100)/100))
#             elif (ry) < -0.05:
#                 # print(event)
#                 print("RIGHT JOY Moved Up :", (math.trunc(ry * 100)/100))

#         # End of New code
#         if event.type == pygame.JOYHATMOTION:
#             # print(pygame.joystick.Joystick(0).get_hat(0)[0])
#             if pygame.joystick.Joystick(0).get_hat(0)[0] == -1:
#                 print("MOVING LEFT")
#             if pygame.joystick.Joystick(0).get_hat(0)[0] == 1:
#                 print("MOVING RIGHT")
#             if pygame.joystick.Joystick(0).get_hat(0)[1] == 1:
#                 print("MOVING UP")
#             if pygame.joystick.Joystick(0).get_hat(0)[1] == -1:
#                 print("MOVING DOWN")

#         if event.type == pygame.JOYBUTTONDOWN:
#             if pygame.joystick.Joystick(0).get_button(0):
#                 player.change_color("blue")
#                 print("Button A has been pressed")
#             elif pygame.joystick.Joystick(0).get_button(1):
#                 player.change_color("red")
#                 print("Button B has been pressed")
#             elif pygame.joystick.Joystick(0).get_button(2):
#                 player.change_color("yellow")
#                 print("Button X has been pressed")
#             elif pygame.joystick.Joystick(0).get_button(3):
#                 player.change_color("black")
#                 print("Button Y has been pressed")
#             elif pygame.joystick.Joystick(0).get_button(4):
#                 player.change_color("green")
#                 print("Button Left Bumper has been pressed")
#             elif pygame.joystick.Joystick(0).get_button(5):
#                 player.change_color("purple")
#                 print("Button Right Bumper has been pressed")

#     # player.move(x + xVel, y + yVel)