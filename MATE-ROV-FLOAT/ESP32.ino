#include <WiFi.h> 
#include <HTTPClient.h> 


const char* WIFI_name = "SBRT";
const char* password = "Robotic$3";

const char* server_name= "192.168.1.117"; 

void setup() {
  Serial.begin(115200); 
  WiFi.begin(WIFI_name, password); 
  while (WiFi.status() != WL_CONNECTED)
  {
    delay (15000); 
    
    Serial.println("Connecting to WiFI..."); 
  }
  Serial.println ("WIFI connected"); 
  Serial.print("IP address is: "); 
  Serial.print(WiFi.localIP()); 
  // put your setup code here, to run once:

}

void loop() {
  if (WiFi.status() == WL_CONNECTED)
  {
    HTTPClient http; 
    http.begin(server_name); 
    http.addHeader("Try-post", "text/plain"); 

    int httpResponse= http.POST ("post from ESP32"); 


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
  }
  else 
  {
    Serial.println("WiFi Connection lost."); 
  }


  // put your main code here, to run repeatedly:

}
