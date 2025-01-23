 # Control Team

This the readme for the control team to get a general summary of what we are trying to do and potential next steps

# What is our Goal?

Goal is to take controller inputs from a usb connected controller to a laptop and send them to the server sided raspberry pi which will control the planar movements of the MROV

Polished End Goal is the MROV uses this dictionary of inputs to move 

Planar movements include:
- Moving forward, backwards
- Strafing left, right
- Turning left, right

These movements will be mapped on the left and right joysticks of an X-Box One Controller

# Explanation of Code

## Client Folder

The Client folder has the code for the laptop (client because it is sending constant information from the controller to the pi)
- To run just cd into the folder and run the python script (python pi.py) and it should be listening to socket connection from the server side

## Server Folder
The Server folder has the code for the RaspberryPi5 (server is retrieving the info and then making then motors move) 
- Go onto the pi and run it on theany or something f5
- There is a com_socket_server file and a 8 motor test code file (the com_socket starts the pi server and the 8 motor tests if the input vectors we sent are correct (general use internal comp motors))

## Sim Folder
The Sim Folder contains the file simulation.py which is just a simple py game simulation to test motor inputs it assumes that the front of the mrov is pointing right
- to run it just connect your controller and cd into it (python simulation.py)

## SRC Folder
The src folder contains the following files: arcadeDrive.py, controller.py, and testMapping.py 
- The arcadeDrive.py just contains the logic for making controller inputs into motor PWM outputs
- The controller.py is the pygame file that reads the controller inputs
- testMapping is a WIP and is working on Langer's suggestion to make the controller more customizable (make right joystick do forward backward, etc)

# Goals for this Semester 
1. Test with motors (like actual motors) - more coding on the pi side
2. Polish Server and Client code: maybe make it send bytes with (some library i forgor)
3. Document recent changes as we go through every meeting
4. maybe implement HTTP URL routing get post requests bs (but i doubt it)
5. Langer's mapping thingy
6. Arash's PID drift correction thingy
7. Documenting Float Team's BS

