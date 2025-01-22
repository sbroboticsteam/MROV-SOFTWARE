#include <WiFi.h> //library for arduino to connect to internet (can be either server or client)
#include <HTTPClient.h> //library for http requests (get, post, etc)
#include <WebServer.h> //dead simple server that works with only 1 simultaenous client ( only handles get and post requests)
#include <ArduinoQueue.h> //library to implement queue https://github.com/EinarArnason/ArduinoQueue

#define QUEUE_IMPLEMENTATION FIFO
#define MAX_WATER_ALLOWED_IN_FLOAT 100 //[TODO]: replace the 100 with the actual max value
#define TARGET_DEPTH 20 //[TODO]: replace the 100 with the actual target depth value
#define SEND_INTERVAL 3000 //[TODO]: replace the 3000 with a good interval value for wait time between sending two consecutive coordinates

struct Coordinate{ //data structure called coordinate with 2 members currentTime and depth
  unsigned long currentTime; 
  int depth; 
}; 

//initializes the Queue (size of 50)
ArduinoQueue<Coordinate> coordinateQueue(50);

//initializes variables
const char* ssid = ""; 
const char* password = "";
int hasStarted = 0; 
int toDescend = 0; 
int toAscend = 0; 

// Create a WebServer object on port 80
WebServer server(80);
char result[100]; 
HTTPClient http; 

unsigned long elapsedTime; 
unsigned long lastSendTime;
int depth = 0; 
String ip_address;
int depth_testing; /*used for testing*/

// Function to handle HTTP requests for connecting with the surface laptop
void handleToStartSignal() {
  if(server.hasArg("ip_address") && (ip_address = server.arg("ip_address"))){ //checks if the server get request has the param ip_address and init it
    if(!hasStarted){ //has started init to 0
        elapsedTime = millis(); //start time
        hasStarted = 1;   
        toDescend = 1; //start to descend
        depth_testing = 2;
        http.begin("http://" + ip_address + ":8000/depth"); //prepares the post req to with url endpoint
        http.addHeader("Content-Type", "text/plain"); 
        http.setTimeout(5000); 
        server.send(200, "text/plain", "Process starts, will use ip_address: " + ip_address);
    }else{
        server.send(400, "text/plain", "Process already started, using ip_address: " + ip_address);
    }
  }else{
    server.send(400, "text/plain", "Missing ip_address");
  }
}

//sets up the server (no calls listen or sent)
void setup() {
  Serial.begin(115200);  //jitt is printing on the serial monitor (Arduino IDE)
  WiFi.begin(ssid, password); //connecting to WiFi

  while (WiFi.status() != WL_CONNECTED) //does the connecting to wifi bs if it isnt connected
  {
    Serial.println("Connecting to WiFi..");
    delay(10000);
  }
  Serial.println("Connected to the WiFi network");
  Serial.print("IP address is: "); 
  Serial.println(WiFi.localIP()); 
  Serial.print("Hostname is: ");
  Serial.println(WiFi.getHostname());

  //Set up server param1 is the url path, param2 is that it has to be a get request, param3 is function to be called when route is there
  server.on("/start_signal", HTTP_GET, handleToStartSignal);
  server.begin(); //starts the server

  /*used for testing*/
  getWaterLevelInFloat();
  getDepth();
  descending();
  ascending();
}

void loop() { 
//loop just keeps sending post requests every interval if it fails it puts it back in the queue and 
//then after it finishes the whole process (ascending) it dequeues what has failed to send
  if(hasStarted /*process has started*/){ //from init (handleStart)
    Serial.println("process starts");
    if(toDescend){
      if(/*getWaterLevelInFloat() <= MAX_WATER_ALLOWED_IN_FLOAT*/ 1) { //[TODO]: write function getWaterLevelInFloat()
        //descending(); //[TODO]: write function descending()
        Serial.println("descending"); 
      }else{
        Serial.println("water exceed allowed amount in float"); 
      }
    }else {
      //ascending(); //[TODO]: write function ascending()
      Serial.println("ascending");
    }
    
    if(millis() - lastSendTime > SEND_INTERVAL /*ready to send the next coordinate*/){ //only sends a post req after interval
      unsigned long time_elapsed_since = millis() - elapsedTime; //total time from start init
      int httpResponse = http.POST(String(time_elapsed_since) + "," + String(depth)); //post req send to url created in http.begin
      
      if(httpResponse < 0){ //fails
        Serial.println("Server post response below 0. Not posted");
        Coordinate coordinate = {time_elapsed_since, depth}; //Put back in queue if post req fails
        coordinateQueue.enqueue(coordinate);
      }else{
        String response = http.getString(); 
        Serial.println(response); 
      }
      depth /*= getDepth()*/ +=depth_testing; //[TODO]: write function getDepth()and remove '+=depth_testing'
      lastSendTime = millis(); 
    }

    //float changes to ascending if the target depth has been reached or max water allowed in float is reached
    if( /*getWaterLevelInFloat() > MAX_WATER_ALLOWED_IN_FLOAT || */toDescend && (depth >= TARGET_DEPTH)){
      toDescend = 0; 
      toAscend = 1;  
      depth_testing = -2;
    //float finish the process if reaches the surface when ascending
    }else if(toAscend && depth <= 0){
      toAscend = 0; 
      hasStarted = 0;  
    }
  }else{
    //Dequeue any remaining coordinates inside queue
    while(!coordinateQueue.isEmpty()){
      Serial.println("Dequeuing");
      Coordinate coordinate = coordinateQueue.dequeue();  
      int httpResponse = http.POST(String(coordinate.currentTime) + "," + String(coordinate.depth));

      if(httpResponse < 0){
        Serial.println("Server post response below 0. Not posted");
        if(depth >= coordinate.depth){
          //If failed again, only try resending the critical coordinate in worse case
          coordinateQueue.enqueue(coordinate);
        }
      }else{
        String response = http.getString(); 
        Serial.println(response); 
      }
    }
    
    Serial.println("Process has not start");
  }
  
  // Handle client requests
  server.handleClient();
}


