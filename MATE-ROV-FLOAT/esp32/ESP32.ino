#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <ArduinoQueue.h> //library to implement queue https://github.com/EinarArnason/ArduinoQueue

#define QUEUE_IMPLEMENTATION FIFO
#define MAX_WATER_ALLOWED_IN_FLOAT 100 //[TODO]: replace the 100 with the actual max value
#define TARGET_DEPTH 20 //[TODO]: replace the 100 with the actual target depth value
#define SEND_INTERVAL 3000 //[TODO]: replace the 3000 with a good interval value for wait time between sending two consecutive coordinates

struct Coordinate{
  unsigned long currentTime; 
  int depth; 
}; 

ArduinoQueue<Coordinate> coordinateQueue(50);

const char* ssid = "NETGEAR56";
const char* password = "rockytulip400";
int hasStarted = 0; 
int descending = 0; 
int ascending = 0; 

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
  if(server.hasArg("ip_address") && (ip_address = server.arg("ip_address"))){
    if(!hasStarted){
        elapsedTime = millis(); 
        hasStarted = 1;   
        descending = 1; //start to descend
        depth_testing = 2;
        http.begin("http://" + ip_address + ":8000/depth");
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

void setup() {
  Serial.begin(115200);  
  WiFi.begin(ssid, password); 

  //Connect to WIFI
  while (WiFi.status() != WL_CONNECTED) 
  {
    Serial.println("Connecting to WiFi..");
    delay(10000);
  }
  Serial.println("Connected to the WiFi network");
  Serial.print("IP address is: "); 
  Serial.println(WiFi.localIP()); 

  //Set up server
  server.on("/start_signal", HTTP_GET, handleToStartSignal);
  server.begin();
}

void loop() {
  if(hasStarted /*process has started*/){
    Serial.println("process starts");
    if(descending){
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
    
    if(millis() - lastSendTime > SEND_INTERVAL /*ready to send the next coordinate*/){
      unsigned long time_elapsed_since = millis() - elapsedTime; 
      int httpResponse = http.POST(String(time_elapsed_since) + "," + String(depth));
      
      if(httpResponse < 0){
        Serial.println("Server post response below 0. Not posted");
        Coordinate coordinate = {time_elapsed_since, depth};
        coordinateQueue.enqueue(coordinate);
      }else{
        String response = http.getString(); 
        Serial.println(response); 
      }
      depth /*= getDepth()*/ +=depth_testing; //[TODO]: write function getDepth()and remove '+=depth_testing'
      lastSendTime = millis(); 
    }

    //float changes to ascending if the target depth has been reached or max water allowed in float is reached
    if( /*getWaterLevelInFloat() > MAX_WATER_ALLOWED_IN_FLOAT || */descending && (depth >= TARGET_DEPTH)){
      descending = 0; 
      ascending = 1;  
      depth_testing = -2;
    //float finish the process if reaches the surface when ascending
    }else if(ascending && depth <= 0){
      ascending = 0; 
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
