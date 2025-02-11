#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <ArduinoQueue.h> //library to implement queue https://github.com/EinarArnason/ArduinoQueue
#include <Wire.h> // For i2c address management
#include <MS5837.h> // Blue robotics library for depth sensor
#include <ArduinoJson.h> // JSON library

#define QUEUE_IMPLEMENTATION FIFO
#define MAX_WATER_ALLOWED_IN_FLOAT 100 //[TODO]: replace the 100 with the actual max value
#define TARGET_DEPTH 2.6 //[TODO]: replace the 100 with the actual target depth value
#define SEND_INTERVAL 3000 // Time between sending coordinates (milliseconds)
#define P1 12
#define P2 27
#define ASCEND_DELAY 45000 // Delay before ascending (milliseconds)

MS5837 sensor; // Create an instance of the depth sensor

// Data structure to send the coordinates to the laptop
struct Coordinate {
  unsigned long currentTime;
  int depth;
};

// Queue datastructure to store the coordinates
ArduinoQueue<Coordinate> coordinateQueue(50);

// Wifi Credentials
const char *ssid = "SBRT";
const char *password = "Robotic$3";

// Flags for function
int hasStarted = 0;
int toDescend = 0;
int toAscend = 0;

// Create a WebServer object on port 80
WebServer server(80);
HTTPClient http;

unsigned long elapsedTime; // Time from start of routine
unsigned long lastSendTime; // Variable to store the last time data was sent
float depth = 0;            // Variable for storing depth from depth sensor
String ip_address;
float init_depth = 0; // Initial depth before procedure

// Function to initialize the depth sensor
void init_depth_sensor() {
  Wire.begin();
  sensor.setModel(MS5837::MS5837_02BA);
  sensor.init();
  sensor.setFluidDensity(1029); // kg/m^3 (997 freshwater, 1029 for seawater)
}

float read_depth() {
  sensor.read();
  return sensor.depth(); // depth in meters
}

// Function to pump water into the float
void descending_float() {
  Serial.println("Descending");
  // Insert code to pump water into the float
  // Uses pins P1 and P2
  digitalWrite(P1, HIGH);
  digitalWrite(P2, LOW);
}

// Function to pump water out of the float
void ascending_float() {
  Serial.println("Ascending");
  // Insert code to pump water out of the float
  // Uses pins P1 and P2
  digitalWrite(P1, LOW);
  digitalWrite(P2, HIGH);
}

// Function to stop pumping water
void stopPump() {
  Serial.println("Stopping Pump");
  // Insert code to stop the pump
  // Uses pins P1 and P2
  digitalWrite(P1, LOW);
  digitalWrite(P2, LOW);
}

// Function to handle HTTP requests for connecting with the surface laptop
void handleToStartSignal() {
  if (server.hasArg("ip_address") && (ip_address = server.arg("ip_address"))) {
    if (!hasStarted) {
      // Record time in ms since the power on of the esp32
      elapsedTime = millis();
      hasStarted = 1; // Toggle process start
      toDescend = 1;  // start to descend

      http.begin("http://" + ip_address + ":8000/depth"); // Init http client
      http.addHeader("Content-Type", "application/json");
      http.setTimeout(5000); // Wait for 5 seconds

      server.send(200, "text/plain",
                  "Process starts, will use ip_address: " + ip_address); // Send
    } else {
      // In case process has already started
      server.send(400, "text/plain",
                  "Process already started, using ip_address: " + ip_address);
    }
  } else {
    // In case ip_address is not provided/matching
    server.send(400, "text/plain", "Missing ip_address");
  }
}

// Function to setup ESP
void setup() {
  // Set BAUD rate to 115200
  Serial.begin(115200);
  pinMode(P1, OUTPUT);
  pinMode(P2, OUTPUT);

  WiFi.begin(ssid, password); // Connect to the wifi network

  // Connect to WIFI
  while (WiFi.status() != WL_CONNECTED) {
    Serial.println("Connecting to WiFi.."); // Print connecting to wifi
    delay(10000); // Wait for 10 seconds to connect to wifi in case signal no bueno
  }

  // Print to console once connected to wifi
  Serial.println("Connected to the WiFi network");
  Serial.print("IP address is: ");
  Serial.println(WiFi.localIP());
  Serial.print("Hostname is: ");
  Serial.println(WiFi.getHostname());

  // Set up server, When there is a get request to /start_signal, call
  // handleToStartSignal function
  server.on("/start_signal", HTTP_GET, handleToStartSignal);
  server.begin();

  // Get initial depth before procedure
  init_depth_sensor(); // Initialize the depth sensor for saltwater
  init_depth = read_depth();
}

void loop() {
  server.handleClient(); // Handle client requests

  if (hasStarted /*process has started*/) {
    Serial.println("process starts");

    depth = read_depth() - init_depth; // Calculate depth relative to initial depth

    if (toDescend) {
      if (depth <= TARGET_DEPTH) {
        Serial.println("descending");
        descending_float(); // Pump water in
      } else {
        Serial.println("TARGET DEPTH Reached");
        toDescend = 0;
        stopPump();
        Serial.println("Pump Stopped, Waiting for 46 Seconds");

        unsigned long holdStartTime = millis();
        while (millis() - holdStartTime < ASCEND_DELAY) {
          server.handleClient(); // Keep handling client requests
          yield();               // Yield to the RTOS
        }
      }
    } else {
      Serial.println("ascending");
      toAscend = 1; // Ascending Function will take care of it
    }

    if (toAscend) {
      if (depth >= 0) {
        Serial.println("ascending");
        ascending_float(); // Pump water out
      } else {
        Serial.println("INIT DEPTH Reached, Process complete");
        toAscend = 0;
        hasStarted = 0;
        stopPump();
      }
    }

    if (millis() - lastSendTime >
        SEND_INTERVAL /*ready to send the next coordinate*/) {
      unsigned long time_elapsed_since = millis() - elapsedTime;

      StaticJsonDocument<200> jsonDocument;
      jsonDocument["time"] = time_elapsed_since;
      jsonDocument["depth"] = depth;

      String payload;
      serializeJson(jsonDocument, payload);

      http.begin("http://" + ip_address + ":8000/depth");
      http.addHeader("Content-Type", "application/json");
      int httpResponse = http.POST(payload);

      if (httpResponse < 0) {
        Serial.println("Server post response below 0. Not posted");
        Coordinate coordinate = {time_elapsed_since, depth};
        coordinateQueue.enqueue(coordinate);
      } else {
        String response = http.getString();
        Serial.println(response);
      }
      lastSendTime = millis();
    }
  } else {
    // Dequeue any remaining coordinates inside queue
    while (!coordinateQueue.isEmpty()) {
      Serial.println("Dequeuing");
      Coordinate coordinate = coordinateQueue.dequeue();

      StaticJsonDocument<200> jsonDocument;
      jsonDocument["time"] = coordinate.currentTime;
      jsonDocument["depth"] = coordinate.depth;

      String payload;
      serializeJson(jsonDocument, payload);

      http.begin("http://" + ip_address + ":8000/depth");
      http.addHeader("Content-Type", "application/json");
      int httpResponse = http.POST(payload);

      if (httpResponse < 0) {
        Serial.println("Server post response below 0. Not posted");
        if (depth >= coordinate.depth) {
          // If failed again, only try resending the critical coordinate in worse
          // case
          coordinateQueue.enqueue(coordinate);
        }
      } else {
        String response = http.getString();
        Serial.println(response);
      }
    }

    Serial.println("Process has not start");
  }
}
 /*
 The code above is the code for the ESP32. The code is responsible for connecting to the WiFi network, initializing the depth sensor, and sending the depth data to the laptop. The code also controls the pump to pump water into the float and out of the float. 
 The code is divided into two main parts: the setup function and the loop function. The setup function is responsible for setting up the ESP32, connecting to the WiFi network, and initializing the depth sensor. The loop function is responsible for handling the main logic of the ESP32. 
 The ESP32 connects to the WiFi network using the  WiFi.begin  function. It then initializes the depth sensor using the  init_depth_sensor  function. The depth sensor is a Blue Robotics MS5837 sensor, which is a pressure sensor that can measure depth in water. The ESP32 reads the depth from the sensor using the  read_depth  function. 
 The ESP32 then sets up a web server using the  WebServer  library. The web server listens for HTTP requests on port 80. When a GET request is made to the  /start_signal  endpoint, the ESP32 calls the  handleToStartSignal  function. The  handleToStartSignal  function checks if an IP address is provided in the request and starts the process if it has not already started. 
 The main logic of the ESP32 is handled in the loop function. If the process has started, the ESP32 reads the depth from the sensor and checks if the target depth has been reached. If the target depth has not been reached, the ESP32 pumps water into the float using the  descending_float  function. If the target depth has been reached, the ESP32 stops pumping water and waits for a delay before ascending. 
 After the delay, the ESP32 starts pumping water out of the float using the  ascending_float  function. Once the initial depth is reached, the process is complete, and the ESP32 stops pumping water. The ESP32 also sends the depth data to the laptop at regular intervals using an HTTP POST request. If the request fails, the ESP32 enqueues the data and tries to resend it later. 
 The ESP32 also dequeues any remaining data in the queue if the process has not started. This ensures that all data is sent to the laptop even if the process has not started. 
 Laptop Code 
 The laptop code is responsible for receiving the depth data from the ESP32 and displaying
 */