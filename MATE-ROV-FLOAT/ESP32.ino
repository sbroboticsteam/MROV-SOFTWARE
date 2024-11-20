#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>

const char* surface_laptop = "http://192.168.0.177:8000/depth"; 

const char* ssid = "SBRT";
const char* password =  "Robotic$3";
int hasStarted = 0; 

// Create a WebServer object on port 80
WebServer server(80);
char result[100]; 

unsigned long elapsedTime; 
int depth = 0; 

// Function to handle HTTP requests
void handleToStartSignal() {
  if(!hasStarted){
    elapsedTime = millis(); 
    hasStarted = 1;   
  }

  Serial.println("Received a request to start the process");
  server.send(200, "text/plain", "Process starts");
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
  Serial.print(WiFi.localIP()); 

  // Define endpoint for GET request
  server.on("/start_signal", HTTP_GET, handleToStartSignal);

  // Start the server
  server.begin();
}
  
void loop() {
  if(hasStarted){//insert Xiang's code
    Serial.println("process starts");
    HTTPClient http; 
    http.begin(surface_laptop);
    http.addHeader("Content-Type", "text/plain"); 
    http.setTimeout(5000);
    
    unsigned long time_elapsed_since = millis() - elapsedTime; 
    int httpResponse = http.POST(String(time_elapsed_since) + "," + String(depth));
    
    if(httpResponse < 0){
      Serial.println("Server post response below 0. Not posted");
    }else{
      String response = http.getString(); 
      Serial.println(response); 
    }
    depth+=2; 
  }else{
   //Serial.println("Process has not start");
  }
  delay(10000);  //Send a request every 10 seconds
  // Handle client requests
  server.handleClient();
}
