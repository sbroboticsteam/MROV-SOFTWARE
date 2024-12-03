#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <ArduinoQueue.h> //library to implement queue https://github.com/EinarArnason/ArduinoQueue


const char* ssid = "MyAltice c998f9";
const char* password = "222-rose-824";
int hasStarted = 0; 

// Create a WebServer object on port 80
WebServer server(80);
char result[100]; 
HTTPClient http; 

unsigned long elapsedTime; 
unsigned long lastSendTime;
int depth = 0; 
String ip_address;

// Function to handle HTTP requests
void handleToStartSignal() {
  if(server.hasArg("ip_address")){
    ip_address = server.arg("ip_address"); 
     if(!hasStarted){
        elapsedTime = millis(); 
        hasStarted = 1;   
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
  
  while (WiFi.status() != WL_CONNECTED) 
  { //Check for the connection
    Serial.println("Connecting to WiFi..");
    delay(5000);
  }
  
  Serial.println("Connected to the WiFi network");
  Serial.print("IP address is: "); 
  Serial.println(WiFi.localIP()); 

  // Define endpoint for GET request
  server.on("/start_signal", HTTP_GET, handleToStartSignal);

  // Start the server
  server.begin();
}
  
void loop() {
  ArduinoQueue<int> intQueue(20); //initialize queue with data (int) and size of 20
  
  if(hasStarted && millis() - lastSendTime > 3000){//insert Xiang's code
    Serial.println("process starts");
    
    unsigned long time_elapsed_since = millis() - elapsedTime; 
    sprintf(result, "Current depth: %d", depth);  //print out current depth 
    
    int httpResponse = http.POST(String(time_elapsed_since) + "," + String(depth));  //if String(depth) doesn't work, change it to String(result)

    // //use a queue, where enqueue adds the element into it
    // intQueue.enqueue(depth); 
    // int number = intQueue.dequeue();  //remove the element from the queue
    // Serial.printf("%d\n", number);    //print to make sure the queue is working correctly(should be the same printed Current depth: ) 
    
    if(httpResponse < 0){
      Serial.println("Server post response below 0. Not posted");
    }else{
      String response = http.getString(); 
      Serial.println(response); 
    }
    depth+=2; 
    lastSendTime = millis();
  }else{
   //Serial.println("Process has not start");
  }
  // Handle client requests
  server.handleClient();
}
