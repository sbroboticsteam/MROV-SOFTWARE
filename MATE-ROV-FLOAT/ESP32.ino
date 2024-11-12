#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
  
const char* ssid = "SBRT";
const char* password =  "Robotic$3";
int hasStarted = 0; 

WebServer server(80);

void handleToStartSignal() {
  hasStarted = 1; 
  server.send(200, "Float Starts");
}

void setup() {
  Serial.begin(115200);  
  WiFi.begin(ssid, password); 
  
  while (WiFi.status() != WL_CONNECTED) { //Check for the connection
    delay(15000);
    Serial.println("Connecting to WiFi..");
  }
  
  Serial.println("Connected to the WiFi network");
  Serial.print("IP address is: "); 
  Serial.print(WiFi.localIP()); 

  server.on("/start_signal", HTTP_GET, handleToStartSignal);
  server.begin();
}
  
void loop() {
 if(WiFi.status()== WL_CONNECTED){   //Check WiFi connection status
  if(hasStarted){
    //insert Xiang's code
    Serial.println("process starts");

  }else{
    Serial.println("Process has not start");
  }
 }else{
    Serial.println("Error in WiFi connection");  
 }
  delay(10000);  //Send a request every 10 seconds
  // Handle client requests
  server.handleClient();
}
