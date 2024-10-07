# VPF

This the repository for the Vertical Profiling Float Team for SBRT 2024 MATE ROV. 

##Project Requirements 
We are programing a vertical profiling float to do the following:
1. Listen for a START signal at the surface of the water then start an automated process to detect the depth of the water.
2. Steps of the automated depth detection process
   2.1 sink into the water until it reaches the depth of 2.5 meters
   2.2 stay at the depth for 2 minutes then start ascending to the surface
   2.3 during the whole process, attemp to send a (time, depth) tuple data point to the surface laptop every 5 seconds
3. Repeat Step 2 TWO TIMES exactly
4. The surface laptop should gather all the (time, depth) tuple data receoved and plot a Depth vs Time graph

##Important Notes: 
- We will write the program for the float in an ESP32, a microcontroller or a tiny computer, using C++
- We will write the program for the surface laptop in python
- To enable data transmission between the float and the laptop, we will use the HTTP communication protocal and use HTTP timeout to decide if a data has been received by the surface laptop 
- We will use a queue to store all the (time, depth) tuple data awaiting to be transmitted in the float
- After receving the START signal, all the following actions on the float should be automated (not controlled by the surface laptop, the program is written on the float
- The float need to program to resent a (time, depth) tuple data if the surface laptop failed to receive the data due to poor network signal underwater

##Q & A
1. Where do we get the real time depth date from?
   - Electrical Team will attach a sensor on the float and provide us with a getCurrentDepth() func as the sensor's API
2. How do we controll the float's movement (sinking and ascending)? 
   - Most likely there will be servo(s) attached on the float where we need to controll the speed and directin of the servo(s) for the float to move 


##Learning resources
1. How to send HTTP request from an ESP32: 
   https://www.youtube.com/watch?app=desktop&v=LiQaPJ9UrSM&t=19s
2. How to set up a HTTP server (to receive and process the request) in python: 
   https://www.youtube.com/watch?v=kogOfxg1c_g
   https://youtu.be/DeFST8tvtuI?si=belyx59lG6xcFqGZ&t=383 


##Task Assignment 
ESP32 Programming Team 
- Connect the ESP32 to the SBRT WIFI 
- Detect the START signal send by the surface laptop (most likely a HTTP GET request) and start the automated process. Reply to the laptop with a 200 status code after successfully start the automated process. 
- Send HTTP POST request to the surface laptop containing a (time, depth) tuple and validate if the laptop has successfully receive the request or not by catching either a HTTP timeout (indicate failure) or a HTTP response with 200 status code (indicate success)
- Program the servo(s) to sink and ascend the float at a proper time 

Surface Laptop Team 
- Set up a python server with the following route
- GET /start
  - Send a HTTP GET request to ESP32 to start the automated process
- POST /depth
  - Store the received (time, depth) data to an array and reply with a 200 status code
- GET /display_graph
  - Display a time vs depth graph using the avaliable data




