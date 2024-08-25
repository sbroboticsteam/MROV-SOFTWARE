import pygame

pygame.joystick.init()
joysticks = [pygame.joystick.Joystick(x) for x in range (pygame.joystick.get_count())]

class Player(object):
    
    def __init__(self):
        self.player = pygame.rect.Rect((300, 400, 50, 50))
        self.color = "white"
        
    def  move(self, x, y):
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

#controller input
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            break
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                print("GOING UP")
                y = -2
            if event.key == pygame.K_DOWN:
                print("GOING DOWN")
                y = 1
            if event.key == pygame.K_RIGHT:
                print("GOING UP")
                x = 1
            if event.key == pygame.K_LEFT:
                print("GOING UP")
                x = -1
        
        if event.type == pygame.KEYUP:
            if event.key == pygame.K_UP:
                print("Stopping")
                y = 0
            if event.key == pygame.K_DOWN:
                print("Stopping")
                y = 0
            if event.key == pygame.K_RIGHT:
                print("Stopping")
                x = 0
            if event.key == pygame.K_LEFT:
                print("Stopping")
                x = 0
            #if pygame.joystick.Joystick(0).get_button(0):
            #    player.change_color("blue")
    
    #x = round()
    #y = round(pygame.K_RIGHT)
    player.move(x, y)
                
    screen.fill((0,0,0))
    player.draw(screen)
    pygame.display.update()
    
    clock.tick(180)
                
#print(joysticks)

