#include <WiFi.h> 
#include <HTTPClient.h> 

const char* WIFI_name = "";
const char* password = "";

const char* server_name= "http://192.168.0.96:8000/depth"; 
char result[50]; 

int dep1 = 10; 
int dep2= 30; 

void setup() {
  Serial.begin(115200); 
  WiFi.begin(WIFI_name, password); 
  while (WiFi.status() != WL_CONNECTED)
  {
    delay (15000); 
    
    Serial.println("Connecting to WiFI..."); 
  }
  Serial.println ("WIFI connected"); 
  // put your setup code here, to run once:

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
  }
  else 
  {
    Serial.println("WiFi Connection lost."); 
  }


  // put your main code here, to run repeatedly:

}
