import pygame
import math

mapping_dict = {
    "UP":
        "DOWN"
}

pygame.joystick.init()
joysticks = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]


# print(joysticks[0].get_numhats())
def arcadeDrive(x,y) -> list[float]:
    """
    turns stick axes into appropriate motor values
    - the motor values are returned as an array of floats (details on the order below)
    """

    maximum = max(abs(x), abs(y))
    total, difference = x + y, x - y
    out = []
    # set speed according to the quadrant that the values are in
    if x >= 0:
        if y >= 0:  # I quadrant
            out = [maximum, difference, difference, maximum]
        else:            # II quadrant
            out = [total, maximum, maximum, total]
    else:
        if y >= 0:  # IV quadrant
            out = [total, -maximum, -maximum, total]
        else:            # III quadrant
            out = [-maximum, difference, difference, -maximum]
    return out

    """
    robot motors:
    - h is the heading / direction of the robot
     _______
    |4     1|
    |  h->  |
    |3_____2|

    """



# class Player(object):

#     def __init__(self):
#         self.player = pygame.rect.Rect((300, 400, 50, 50))
#         self.color = "white"

#     def move(self, x, y):
#         self.player.move_ip((1.1 * x, 1.1* y))

#     def change_color(self, color):
#         self.color = color

#     def draw(self, game_screen):
#         pygame.draw.rect(game_screen, self.color, self.player)

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
        y = joystick.get_axis(1)  # Y-axis
        ry = joystick.get_axis(3)
        rx = joystick.get_axis(2)
        rT = joystick.get_axis(5)
        lT = joystick.get_axis(4)
        
        buttons = {f"button_{i}": joystick.get_button(i) for i in range(joystick.get_numbuttons())}
        hats = [joystick.get_hat(i) for i in range(joystick.get_numhats())]
        motor_values = arcadeDrive(x, y)
        
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


        
# player = Player()
# clock = pygame.time.Clock()
# screen = pygame.display.set_mode((800, 600))
# x = 0
# y = 0
# speed = 0
# xVel = 0
# yVel = 0
# rx = 0
# ry = 0
# running = True

# leftSim = 0.0
# rightSim = 0.0

# def drawSim(x,y):
#     inputs = arcadeDrive(x,y)
#     leftSim = inputs[0]
#     rightSim = inputs[1]
#     width = 800
#     height = 600
#     pygame.draw.line(screen,"red",pygame.Vector2(width/2 - 50,height/2), pygame.Vector2(width/2 - 50, leftSim * 100 + height/2), 25)
#     pygame.draw.line(screen,"blue",pygame.Vector2(width/2 + 50,height/2), pygame.Vector2(width/2 + 50, rightSim * 100 + height/2), 25)

# # print("Right Trigger:", pygame.joystick.Joystick(0).get_axis(5))

# # controller input
# while running or KeyboardInterrupt:
#     for event in pygame.event.get():
#         if event.type == pygame.QUIT:
#             running = False
#             pygame.quit()
#             break

#         if event.type == pygame.JOYAXISMOTION:            
#             y = pygame.joystick.Joystick(0).get_axis(1)
#             x = pygame.joystick.Joystick(0).get_axis(0)
#             threshold = 0.1
            
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
#             # print(ry)
#             # print(rx)

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

#     screen.fill((0, 0, 0))
#     player.draw(screen)
#     drawSim(x,y)
#     pygame.display.update()

#     clock.tick(180)

# print(joysticks)


