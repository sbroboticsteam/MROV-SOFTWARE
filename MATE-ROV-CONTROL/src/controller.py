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

class Player(object):

    def __init__(self):
        self.player = pygame.rect.Rect((300, 400, 50, 50))
        self.color = "white"

    def move(self, x, y):
        self.player.move_ip((x, y))

    def change_color(self, color):
        self.color = color

    def draw(self, game_screen):
        pygame.draw.rect(game_screen, self.color, self.player)


pygame.init

player = Player()
clock = pygame.time.Clock()
screen = pygame.display.set_mode((800, 600))
x = 0
y = 0
speed = 0
# xVel = 0
# yVel = 0
rx = 0
ry = 0

# print("Right Trigger:", pygame.joystick.Joystick(0).get_axis(5))

# controller input
while True or KeyboardInterrupt:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            break

        if event.type == pygame.JOYAXISMOTION:
            y = pygame.joystick.Joystick(0).get_axis(1)
            x = pygame.joystick.Joystick(0).get_axis(0)
            threshold = 0.1
            

            # Check and print the direction based on the axis values
            if x < -threshold:  # Left movement
                print(f"LEFT JOY Moving Left: {math.trunc(x* 100) / 100}")
            elif x > threshold:  # Right movement
                print(f"LEFT JOY Moving Right: {math.trunc(x* 100) / 100}")
            
            if y < -threshold:  # Up movement
                print(f"LEFT JOY Moving Up: {math.trunc(y* 100) / 100}")
            elif y > threshold:  # Down movement
                print(f"LEFT JOY Moving Down: {math.trunc(y* 100) / 100}")
            # print("Y", math.trunc(x* 100) / 100)
            # print("X", math.trunc(y* 100) / 100)
            
            lefttrigger = pygame.joystick.Joystick(0).get_axis(4)
                # if speed < 5:
                #     speed += 1
            if lefttrigger > 0.1:
                print('leftTrigger', {math.trunc(lefttrigger * 100) / 100})
            righttrigger = pygame.joystick.Joystick(0).get_axis(5)
                # if speed > 0:
                #     speed -= 1
            if righttrigger > 0.1:
                print('rightTrigger', {math.trunc(righttrigger * 100) / 100})
            # elif round(pygame.joystick.Joystick(0).get_axis(1) * 1000) == 1:
            # elif round(pygame.joystick.Joystick(0).get_axis(0) * 1000) == 1:
            # xVel = speed * abs(round(pygame.joystick.Joystick(0).get_axis(0))) -- Left trigger speed
            # yVel = speed * abs(round(pygame.joystick.Joystick(0).get_axis(1))) -- Left triger speed up
            # print("Y", y)
            # print(x)
            # print(speed)
            # if xVel > 0:
            #     print("X position", x + xVel)
            #     print("Y position", y + yVel)
            # if yVel > 0:
            #     print("X position", x + xVel)
            #     print("Y position", y + yVel)

        # Following is right stick controls
        if event.type == pygame.JOYAXISMOTION:
            ry = pygame.joystick.Joystick(0).get_axis(3)
            rx = pygame.joystick.Joystick(0).get_axis(2)
            # print(ry)
            # print(rx)

            if (rx) > 0.05:
                 # print(event)
                 print ("RIGHT JOY Moved right :", (math.trunc(rx * 100)/100))
            elif (rx) < -0.05:
                # print(event)
                 print("RIGHT JOY Moved left :", (math.trunc(rx * 100)/100))
            if (ry) > 0.05:  # Issue calculating y axis
                # print(event)
              print ("RIGHT JOY Moved Down :", (math.trunc(ry * 100)/100))
            elif (ry) < -0.05:
                # print(event)
                print("RIGHT JOY Moved Up :", (math.trunc(ry * 100)/100))


        # End of New code

        if event.type == pygame.JOYHATMOTION:
            # print(pygame.joystick.Joystick(0).get_hat(0)[0])
            if pygame.joystick.Joystick(0).get_hat(0)[0] == -1:
                print("MOVING LEFT")
            if pygame.joystick.Joystick(0).get_hat(0)[0] == 1:
                print("MOVING RIGHT")
            if pygame.joystick.Joystick(0).get_hat(0)[1] == 1:
                print("MOVING UP")
            if pygame.joystick.Joystick(0).get_hat(0)[1] == -1:
                print("MOVING DOWN")

        if event.type == pygame.JOYBUTTONDOWN:
            if pygame.joystick.Joystick(0).get_button(0):
                player.change_color("blue")
                print("Button A has been pressed")
            elif pygame.joystick.Joystick(0).get_button(1):
                player.change_color("red")
                print("Button B has been pressed")
            elif pygame.joystick.Joystick(0).get_button(2):
                player.change_color("yellow")
                print("Button X has been pressed")
            elif pygame.joystick.Joystick(0).get_button(3):
                player.change_color("black")
                print("Button Y has been pressed")
            elif pygame.joystick.Joystick(0).get_button(4):
                player.change_color("green")
                print("Button Left Bumper has been pressed")
            elif pygame.joystick.Joystick(0).get_button(5):
                player.change_color("purple")
                print("Button Right Bumper has been pressed")

        # if event.type == pygame.KEYDOWN:
        #     if event.key == pygame.K_UP:
        #         print("GOING UP")
        #         y = -2
        #     if event.key == pygame.K_DOWN:
        #         print("GOING DOWN")
        #         y = 1
        #     if event.key == pygame.K_RIGHT:
        #         print("GOING UP")
        #         x = 1
        #     if event.key == pygame.K_LEFT:
        #         print("GOING UP")
        #         x = -1

        # if event.type == pygame.KEYUP:
        #     if event.key == pygame.K_UP:
        #         print("Stopping")
        #         y = 0
        #     if event.key == pygame.K_DOWN:
        #         print("Stopping")
        #         y = 0
        #     if event.key == pygame.K_RIGHT:
        #         print("Stopping")
        #         x = 0
        #     if event.key == pygame.K_LEFT:
        #         print("Stopping")
        #         x = 0

    # y = round(pygame.joystick.Joystick(0).get_axis(1) * 1000) /1000
    # x = round(pygame.joystick.Joystick(0).get_axis(0) * 1000) /1000
    # xVel = speed * abs(round(pygame.joystick.Joystick(0).get_axis(0)))
    # yVel = speed * abs(round(pygame.joystick.Joystick(0).get_axis(1)))
    # # print("Y", y)
    # # print(x)
    # # print(speed)
    # print("X position", x + xVel)
    # print("Y position", y + yVel)
    player.move(x, y)

    screen.fill((0, 0, 0))
    player.draw(screen)
    pygame.display.update()

    clock.tick(180)

# print(joysticks)


