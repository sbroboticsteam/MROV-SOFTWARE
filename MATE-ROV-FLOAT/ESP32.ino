#include <WiFi.h> 
#include <HTTPClient.h> 

const char* WIFI_name = "";
const char* password = "";

const char* server_name= "http://192.168.0.96:8000/depth"; 
char result[50]; 

// Create a WebServer object on port 80
WebServer server(80);

//Testing data 
void handleRoot() {
  server.send(200, "text/html", "<html><body><h1>Hello from ESP32!</h1></body></html>");
}
int dep1 = 10; 
int dep2= 30; 

void setup() {
  Serial.begin(115200); 
  WiFi.begin(WIFI_name, password); 
  while (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("Connecting to WiFI..."); 
    delay (15000); 
  }
  Serial.println ("WIFI connected"); 
  Serial.print("IP address is: "); 
  Serial.print(WiFi.localIP()); 

  // Define endpoint for GET request
  server.on("/start_signal", HTTP_GET, handleRoot);
  // Start the server
  server.begin();
}

void loop() {
  if (WiFi.status() == WL_CONNECTED)
  {
    HTTPClient http; 
    http.begin(server_name); 
    http.addHeader("Content-Type", "text/plain"); 
    
    sprintf(result, "First depth: %d, sec: %d", dep1,dep2 ); 
    int httpResponse = http.POST (String(result)); 

    if (httpResponse<=0)
    {
      delay(1500); 
      Serial.println("Server post response below 0. Not posted"); 
    }
    else 
    {
      String response= http.getString();  //get the string from http 
      Serial.println(response);
    }
    // Handle client requests
    server.handleClient();
  }
  else 
  {
    Serial.println("WiFi Connection lost."); 
  }
}
