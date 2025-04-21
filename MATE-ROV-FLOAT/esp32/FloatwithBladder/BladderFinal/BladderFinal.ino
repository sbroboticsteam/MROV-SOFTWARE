#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <cppQueue.h>  // <--- "cppQueue" library for FIFO with peek() & drop()
#include <Wire.h>
#include <MS5837.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>

// -------------------- CONFIGURATION --------------------
#define WIFI_SSID       "SBRT"
#define WIFI_PASSWORD   "Robotic$3"
#define COMPANY_NUMBER  6969

// -------- RSSI THRESHOLD (dBm) --------
#define RSSI_THRESHOLD  -70

// NeoPixel on GPIO0, powering from GPIO2
#define NEOPIXEL_DATA_PIN   0
#define NEOPIXEL_POWER_PIN  2
#define NUM_PIXELS          1

// Data capture intervals (milliseconds)
#define NORMAL_READ_INTERVAL       2000
#define VELOCITY_READ_INTERVAL     20  // faster rate for velocity testing

// How many items to attempt to send at once
#define SEND_BATCH_SIZE     10

// ----------------- NEW: Pump control -----------------
#define PUMP_DESC_PIN 12   // Pump control pin for descending (fill ballast)
#define PUMP_ASC_PIN  27   // Pump control pin for ascending (empty ballast)

// -------------------- PID Control Variables --------------------
#define TARGET_DEPTH 2.625  // Middle of our range (2.5 to 2.75)
#define DEPTH_TOLERANCE 0.125  // ±0.125m from target (gives us 2.5 to 2.75 range)

// PID coefficients - you'll need to tune these
float Kp = 5.0;    // Proportional gain
float Ki = 0.02;   // Integral gain
float Kd = 2.0;    // Derivative gain

// PID state variables
float integral = 0.0;
float previousError = 0.0;
unsigned long lastPidTime = 0;

// Near the PID Control Variables and other configurations
// Default wait time in milliseconds (45 seconds = 45000 ms)
unsigned long routineWaitTime = 45000;

// PID output will be between -100 (full ascend) and +100 (full descend)
int pidOutput = 0;

// Change this function signature and implementation
int calculatePid(float currentDepth, float* errorOut) {
  unsigned long currentTime = millis();
  float deltaTime = (currentTime - lastPidTime) / 1000.0; // in seconds
  
  // Only update PID if we have a reasonable delta time
  if (deltaTime < 0.01 || lastPidTime == 0) {
    lastPidTime = currentTime;
    *errorOut = 0;
    return 0;
  }
  
  // Calculate error (positive error means we need to descend more)
  float error = TARGET_DEPTH - currentDepth;
  *errorOut = error;  // Set the output parameter
  
  // Rest of the function remains the same
  integral += error * deltaTime;
  // Limit integral to prevent excessive windup
  if (integral > 20) integral = 20;
  if (integral < -20) integral = -20;
  
  // Calculate derivative
  float derivative = (error - previousError) / deltaTime;
  
  // Calculate PID output
  int output = int(Kp * error + Ki * integral + Kd * derivative);
  
  // Limit output to -100 to +100
  if (output > 100) output = 100;
  if (output < -100) output = -100;
  
  // Update state for next iteration
  previousError = error;
  lastPidTime = currentTime;
  
  return output;
}

// Function to control pump based on PID output
void applyPidToPump(int pidOutput, String* pumpStatusOut) {
  // Define a deadband where we turn off the pump (near zero)
  if (pidOutput > 10) {
    // Need to descend (positive output)
    pumpDescend();
    *pumpStatusOut = "Descending";
    Serial.printf("PID: Descending (output: %d)\n", pidOutput);
  } 
  else if (pidOutput < -10) {
    // Need to ascend (negative output)
    pumpAscend();
    *pumpStatusOut = "Ascending";
    Serial.printf("PID: Ascending (output: %d)\n", pidOutput);
  } 
  else {
    // Within deadband - hold position
    pumpOff();
    *pumpStatusOut = "Off";
    Serial.println("PID: Holding position");
  }
}

// Add this near your other flag variables (around line 110)
volatile bool pidControlActive = false;  // Whether to use PID control outside of routine mode

// ----------------- NEW: Routine state machine -----------------
enum RoutineState {
  R_IDLE,
  R_DESCENDING,
  R_WAITING,
  R_ASCENDING
};

volatile bool routineActive = false;
volatile RoutineState routineState = R_IDLE;
unsigned long routineWaitStart = 0;

// -------------------- NEW: Velocity Control Variables --------------------
// Maximum allowed descent velocity (m/s) when the ballast tank is full.
float maxDescentVelocity = 0.18;  // You can change this value later

// Maximum allowed ascent velocity (m/s).
float maxAscentVelocity = 0.1;   // Change as desired

// Variables for tracking previous sensor reading (for velocity computation)
unsigned long previousTime = 0;
float previousDepth = 0.0;

// Shared flags
volatile bool wifiFlag   = false;  // True if WiFi connected & RSSI good
volatile bool hasStarted = false;  // True after /start_signal is called

// Global variable for current data capture interval (modifiable via commands)
volatile unsigned long currentReadInterval = NORMAL_READ_INTERVAL;

// ------------- Queue to hold data -------------
struct Measurement {
  unsigned long timeSinceStart; // in milliseconds
  float depth;
  float pressure;
  int   companyNum;
  // New debugging fields
  float velocity;      // Current velocity in m/s
  int   pidOutput;     // Current PID output (-100 to 100)
  float pidError;      // Current error (target - current)
  String pumpStatus;   // Current pump status (ascending/descending/off)
};

// Function prototype - add this before implementing the function
bool sendMeasurements(Measurement* measurements, int count);

// Use cppQueue: record size = sizeof(Measurement), capacity = 400, FIFO, no overwrite
cppQueue measurementQueue(sizeof(Measurement), 800, FIFO, false);

// Web server and HTTP client
WebServer server(80);
HTTPClient http;

// Depth sensor
MS5837 sensor;

// NeoPixel strip object
Adafruit_NeoPixel strip(NUM_PIXELS, NEOPIXEL_DATA_PIN, NEO_GRB + NEO_KHZ800);

// We'll store these to compute relative depth
unsigned long startTime    = 0;
float initialDepth         = 0.0;

// IP address where we post data
String laptopIpAddress = "";

// -------------------- Helper: Set NeoPixel color --------------------
void setStripColor(uint8_t r, uint8_t g, uint8_t b) {
  strip.setPixelColor(0, strip.Color(r, g, b));
  strip.show();
}

// Add this new function
bool sendMeasurements(Measurement* measurements, int count) {
  if (!wifiFlag || laptopIpAddress.isEmpty() || count <= 0) {
    return false;
  }

  DynamicJsonDocument jsonDoc(1024 * 2);  // Increased buffer size for debugging data
  JsonArray dataArray = jsonDoc.createNestedArray("data");

  for (int i = 0; i < count; i++) {
    JsonObject obj = dataArray.createNestedObject();
    obj["time"] = measurements[i].timeSinceStart / 1000.0;
    obj["depth"] = measurements[i].depth;
    obj["pressure"] = measurements[i].pressure;
    obj["company"] = measurements[i].companyNum;
    
    // Add debugging info
    obj["velocity"] = measurements[i].velocity;
    obj["pid_output"] = measurements[i].pidOutput;
    obj["pid_error"] = measurements[i].pidError;
    obj["pump_status"] = measurements[i].pumpStatus;
  }

  String jsonString;
  serializeJson(jsonDoc, jsonString);

  // Set up HTTP client and POST request
  http.begin("http://" + laptopIpAddress + ":8000/depth");
  http.addHeader("Content-Type", "application/json");
  int httpResponseCode = http.POST(jsonString);

  bool success = (httpResponseCode == 200);
  if (!success) {
    Serial.print("Error sending data. HTTP Response code: ");
    Serial.println(httpResponseCode);
  }
  http.end();
  return success;
}

// -------------------- NEW: Pump control helper functions --------------------
void pumpDescend() {
  digitalWrite(PUMP_DESC_PIN, HIGH);
  digitalWrite(PUMP_ASC_PIN, LOW);
}

void pumpAscend() {
  digitalWrite(PUMP_DESC_PIN, LOW);
  digitalWrite(PUMP_ASC_PIN, HIGH);
}

void pumpOff() {
  digitalWrite(PUMP_DESC_PIN, LOW);
  digitalWrite(PUMP_ASC_PIN, LOW);
}

// -------------------- /set_pid handler --------------------
void handleSetPid() {
  if (server.hasArg("kp")) {
    Kp = server.arg("kp").toFloat();
  }
  if (server.hasArg("ki")) {
    Ki = server.arg("ki").toFloat();
  }
  if (server.hasArg("kd")) {
    Kd = server.arg("kd").toFloat();
  }
  
  String response = "PID parameters updated: Kp=" + String(Kp) + 
                   ", Ki=" + String(Ki) + 
                   ", Kd=" + String(Kd);
  server.send(200, "text/plain", response);
  Serial.println(response);
}

// -------------------- /set_wait_time handler --------------------
void handleSetWaitTime() {
  if (server.hasArg("seconds")) {
    int seconds = server.arg("seconds").toInt();
    if (seconds > 0) {
      routineWaitTime = seconds * 1000; // Convert to milliseconds
      String response = "Wait time updated to " + String(seconds) + " seconds";
      server.send(200, "text/plain", response);
      Serial.println(response);
    } else {
      server.send(400, "text/plain", "Invalid wait time. Please provide a positive number of seconds.");
    }
  } else {
    server.send(400, "text/plain", "Missing 'seconds' parameter");
  }
}

// -------------------- /start_signal handler --------------------
void handleStartSignal() {
  if (server.hasArg("ip_address")) {
    laptopIpAddress = server.arg("ip_address");
    if (!hasStarted) {
      hasStarted = true;
      pidControlActive = false; // Ensure PID is off by default
      startTime = millis();
      sensor.read();
      initialDepth = sensor.depth();  // baseline depth
      
      // Reset velocity tracking variables when starting
      previousTime = 0;
      previousDepth = 0.0;
      
      // Note: we're not forcing pump off when starting,
      // to allow independent pump control
      
      server.send(200, "text/plain",
        "Data transmission started. Will post to " + laptopIpAddress + ":8000/depth");
    } else {
      server.send(200, "text/plain",
        "Already started. Current IP: " + laptopIpAddress);
    }
  } else {
    server.send(400, "text/plain", "Missing ip_address query parameter");
  }
}

// -------------------- /stop_signal handler --------------------
void handleStopSignal() {
  // Reset float state
  hasStarted = false;
  pidControlActive = false;  // Make sure PID control is off when stopping
  routineActive = false;     // Make sure routine is stopped
  measurementQueue.flush();
  
  // Reset timing variables and velocity tracking
  startTime = millis();
  initialDepth = 0.0;
  previousTime = 0;
  previousDepth = 0.0;

  // Also restore the normal data capture rate
  currentReadInterval = NORMAL_READ_INTERVAL;
  routineState = R_IDLE;
  
  // Note: we're not turning the pump off when stopping,
  // to allow independent pump control
  
  server.send(200, "text/plain", "Float has been stopped and reset to initial state.");
}

// -------------------- /start_velocity handler --------------------
void handleStartVelocity() {
  if (!hasStarted) {
    server.send(400, "text/plain", "Float not started yet. Please start the float first.");
    return;
  }
  currentReadInterval = VELOCITY_READ_INTERVAL;
  server.send(200, "text/plain", "Velocity testing started. Data capture rate updated.");
}

// -------------------- /stop_velocity handler --------------------
void handleStopVelocity() {
  if (!hasStarted) {
    server.send(400, "text/plain", "Float not started yet. Cannot stop velocity testing.");
    return;
  }
  currentReadInterval = NORMAL_READ_INTERVAL;
  server.send(200, "text/plain", "Velocity testing stopped. Data capture rate reverted to normal.");
}

// -------------------- /set_velocity handler --------------------
void handleSetVelocity() {
  if (server.hasArg("descent")) {
    maxDescentVelocity = server.arg("descent").toFloat();
  }
  if (server.hasArg("ascent")) {
    maxAscentVelocity = server.arg("ascent").toFloat();
  }
  
  String response = "Velocity limits updated: Descent=" + String(maxDescentVelocity) + 
                   " m/s, Ascent=" + String(maxAscentVelocity) + " m/s";
  server.send(200, "text/plain", response);
  Serial.println(response);
}

// -------------------- /start_routine handler --------------------
void handleStartRoutine() {
  if (!hasStarted) {
    server.send(400, "text/plain", "Float not started yet. Please start the float first.");
    return;
  }
  if (!routineActive) {
    routineActive = true;
    routineState = R_DESCENDING;
    
    // Reset velocity tracking when starting routine
    previousTime = 0;
    previousDepth = 0.0;
    
    // Reset PID variables
    integral = 0.0;
    previousError = 0.0;
    lastPidTime = 0;
    
    server.send(200, "text/plain", "Routine started: Descending initiated.");
    Serial.println("Routine started: Descending initiated.");
  } else {
    server.send(200, "text/plain", "Routine already active.");
  }
}
// -------------------- NEW: Pump control endpoints --------------------
void handlePumpAscend() {
  pumpAscend();
  server.send(200, "text/plain", "Pump ascending initiated.");
  Serial.println("Pump ascending initiated.");
}

void handlePumpDescend() {
  pumpDescend();
  server.send(200, "text/plain", "Pump descending initiated.");
  Serial.println("Pump descending initiated.");
}

void handlePumpStop() {
  pumpOff();
  server.send(200, "text/plain", "Pump stopped.");
  Serial.println("Pump stopped.");
}

// Add this new handler function (around line 345)
// -------------------- /toggle_pid_control handler --------------------
void handleTogglePidControl() {
  pidControlActive = !pidControlActive;
  String status = pidControlActive ? "enabled" : "disabled";
  
  if (!pidControlActive) {
    // Make sure to turn off the pump when disabling PID
    pumpOff();
  }
  
  String response = "PID control outside of routine mode is now " + status;
  server.send(200, "text/plain", response);
  Serial.println(response);
}

// -------------------- TASK on CORE 0: WiFi & WebServer --------------------
void TaskWifiServer(void * pvParameters) {
  (void) pvParameters;  // unused

  for (;;) {
    // Handle incoming HTTP requests
    server.handleClient();

    // Check WiFi connection + RSSI
    if (WiFi.status() == WL_CONNECTED) {
      long rssi = WiFi.RSSI();
      wifiFlag = (rssi >= RSSI_THRESHOLD);
    } else {
      wifiFlag = false;
    }

    // Avoid hogging the CPU
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }
}

// -------------------- TASK on CORE 1: Sensor Reading, Routine, & Queue Send --------------------
void TaskSensorAndSending(void * pvParameters) {
  (void) pvParameters;
  unsigned long lastReadTime = 0;
  unsigned long currentMillis = 0;
  unsigned long lastSendTime = 0; // Add this to control sending frequency
  float currentVelocity = 0.0;
  String pumpStatus = "Standby";
  float pidError = 0.0;

  for (;;) {
    currentMillis = millis();

    // Always read sensor data, even if not started
    // This allows pump control to work regardless of hasStarted state
    sensor.read();
    float currentDepth = sensor.depth() - initialDepth;

    // Calculate velocity if we have previous readings
    if (previousTime > 0) {
      unsigned long dt_ms = currentMillis - previousTime;
      if (dt_ms > 0) {
        float dt = dt_ms / 1000.0; // convert to seconds
        currentVelocity = (currentDepth - previousDepth) / dt;
      }
    }

    // Always update previous values for velocity calculation
    previousTime = currentMillis;
    previousDepth = currentDepth;

    // -------------------- Routine State Machine --------------------
    // Only process routine and PID if started
    if (hasStarted) {
        // Routine State Machine
      if (routineActive) {
        switch (routineState) {
          case R_DESCENDING: {
            pumpStatus = "Routine-Descend";
            // --- Descent Velocity Check ---
            if (previousTime > 0) {
              // Apply velocity limits only when routine is active
              if (currentVelocity > maxDescentVelocity) {
                // Exceeded allowed descent velocity; stop the pump temporarily.
                pumpOff();
                pumpStatus = "Routine-LimitD";
                Serial.printf("ROUTINE MONITOR: Descent velocity (%.3f m/s) exceeded maximum (%.3f m/s). Pump paused.\n", 
                              currentVelocity, maxDescentVelocity);
                // Skip normal descending logic this loop.
                break;
              }
            }
            // Within allowed velocity -> keep descending
            pumpDescend();
            // Check if target depth reached
            if (currentDepth >= 2.5) {
              pumpOff();
              routineState = R_WAITING;
              routineWaitStart = currentMillis;
              Serial.println("Routine: Target depth reached. Holding position...");
            }
            break;
          }
          case R_WAITING: {
            pumpStatus = "Routine-Wait";
            // Hold for 45 seconds (changed from 42 seconds)
            if (currentMillis - routineWaitStart >= routineWaitTime) {
              pumpAscend();
              routineState = R_ASCENDING;
              // Reset PID state variables
              integral = 0.0;
              previousError = 0.0;
              lastPidTime = 0;
              pumpStatus = "Routine-Ascend";
              Serial.println("Routine: Hold complete. Ascending initiated...");
            } 
            else {
              // Use PID to maintain depth between 2.5 and 2.75 meters
              pidOutput = calculatePid(currentDepth, &pidError);
              
              // Set pumpStatus based on PID output
              if (pidOutput > 10) {
                pumpDescend();
                pumpStatus = "PID-Descend";
              } else if (pidOutput < -10) {
                pumpAscend();
                pumpStatus = "PID-Ascend";
              } else {
                pumpOff();
                pumpStatus = "PID-Hold";
              }
              
              // Debug output
              Serial.printf("ROUTINE MONITOR: Waiting: Depth=%.3f, Target=%.3f, PID Output=%d, Error=%.3f\n", 
                            currentDepth, TARGET_DEPTH, pidOutput, pidError);
              
              // We also want to check if we're outside our allowed range
              if (currentDepth < 2.5) {
                Serial.println("WARNING: Depth too shallow (<2.5m)");
              } 
              else if (currentDepth > 2.75) {
                Serial.println("WARNING: Depth too deep (>2.75m)");
              }
            }
            break;
          }
          case R_ASCENDING: {
            pumpStatus = "Routine-Ascend";
            // --- Ascent Velocity Check ---
            if (previousTime > 0) {
              // Apply velocity limits only when routine is active
              // If velocity < -maxAscentVelocity => speed is too high (negative = going up)
              if (currentVelocity < -maxAscentVelocity) {
                pumpOff();
                pumpStatus = "Routine-LimitA";
                Serial.printf("ROUTINE MONITOR: Ascent velocity (%.3f m/s) exceeded maximum (%.3f m/s). Pump paused.\n", 
                              currentVelocity, maxAscentVelocity);
                // Skip normal ascending logic this loop.
                break;
              }
            }
            // Within allowed velocity -> keep ascending
            pumpAscend();
            if (currentDepth <= 0.5) {
              pumpOff();
              routineState = R_IDLE;
              routineActive = false;
              pumpStatus = "Complete";
              Serial.println("Routine: Ascended. Routine complete.");
            }
            break;
          }
          case R_IDLE:
          default:
            pumpStatus = "Routine-Idle";
            break;
        }
      } 
      else if (pidControlActive) {
        // PID control outside of routine
        pidOutput = calculatePid(currentDepth, &pidError);
        
        // Set pump status based on PID output
        if (pidOutput > 10) {
          pumpDescend();
          pumpStatus = "Descending";
        } else if (pidOutput < -10) {
          pumpAscend();
          pumpStatus = "Ascending";
        } else {
          pumpOff();
          pumpStatus = "Off";
        }
    }

    // Data collection and queueing
    if ((currentMillis - lastReadTime) >= currentReadInterval) {
      lastReadTime = currentMillis;
      float pressure = sensor.pressure();
      unsigned long elapsed = currentMillis - startTime;

      Measurement m;
      m.timeSinceStart = elapsed;
      m.depth          = currentDepth;
      m.pressure       = pressure;
      m.companyNum     = COMPANY_NUMBER;
      m.velocity       = currentVelocity;
      m.pidOutput      = pidOutput;
      m.pidError       = pidError;
      m.pumpStatus     = pumpStatus;

      if (!measurementQueue.push(&m)) {
        Serial.println("Queue is full, could not push new measurement!");
      } else {
        Serial.printf("DATA: time=%lu ms, depth=%.3f m, vel=%.3f m/s, PID=%d, err=%.3f, pump=%s\n",
                    elapsed, currentDepth, currentVelocity, pidOutput, pidError, pumpStatus.c_str());
      }
    }
  } 
  else {
    // Not started
    setStripColor(255, 0, 0); // RED
  }
    // Always attempt to send data if WiFi is connected
    if (wifiFlag && !measurementQueue.isEmpty()) {
      // Only rate-limit transmissions if we're not testing velocity
      if ((currentReadInterval == VELOCITY_READ_INTERVAL) || (currentMillis - lastSendTime >= 500)) {
          lastSendTime = currentMillis;
            
          // Create an array to hold the batch of measurements
          Measurement batch[SEND_BATCH_SIZE];
          int batchSize = 0;
          
          // Fill the batch array with measurements from the queue
          for (int i = 0; i < SEND_BATCH_SIZE; i++) {
            if (measurementQueue.isEmpty()) break;
            
            Measurement frontItem;
            if (!measurementQueue.peek(&frontItem)) break;
            
            batch[batchSize++] = frontItem;
            measurementQueue.drop(); // Remove from queue
          }
          
          if (batchSize > 0) {
            // Send the batch
            if (sendMeasurements(batch, batchSize)) {
              Serial.printf("Sent batch of %d measurements\n", batchSize);
              setStripColor(0, 0, 255); // LED BLUE
            } else {
              // Failed to send, put measurements back in queue
              Serial.println("Failed to send batch. Re-queueing measurements...");
              for (int i = batchSize - 1; i >= 0; i--) {
                if (!measurementQueue.push(&batch[i])) {
                  Serial.println("Queue full while re-queueing. Data lost!");
                  break;
                }
              }
            }
          }
      }
    }

    // 4) Update LED based on WiFi and queue state
    if (!wifiFlag) {
      setStripColor(255, 0, 0); // RED if WiFi is poor
    } else {
      // GREEN if queue is empty, YELLOW if not
      setStripColor(measurementQueue.isEmpty() ? 0 : 255,
                    measurementQueue.isEmpty() ? 255 : 255,
                    measurementQueue.isEmpty() ? 0 : 0);
    }

    vTaskDelay(50 / portTICK_PERIOD_MS);
  }
}

// -------------------- SETUP --------------------
void setup() {
  Serial.begin(115200);

  // Set NeoPixel power pin and initialize strip
  pinMode(NEOPIXEL_POWER_PIN, OUTPUT);
  digitalWrite(NEOPIXEL_POWER_PIN, HIGH);
  strip.begin();
  strip.setBrightness(50);
  setStripColor(255, 0, 0);  // LED RED initially

  // Set up pump control pins
  pinMode(PUMP_DESC_PIN, OUTPUT);
  pinMode(PUMP_ASC_PIN, OUTPUT);
  pumpOff(); // Ensure pump is off initially

  // Connect to WiFi (blocking)
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  // Set up HTTP server routes
  server.on("/start_signal", HTTP_GET, handleStartSignal);
  server.on("/stop_signal", HTTP_GET, handleStopSignal);
  server.on("/start_velocity", HTTP_GET, handleStartVelocity);
  server.on("/stop_velocity", HTTP_GET, handleStopVelocity);
  server.on("/start_routine", HTTP_GET, handleStartRoutine);
  server.on("/set_pid", HTTP_GET, handleSetPid);  // New endpoint
  server.on("/set_velocity", HTTP_GET, handleSetVelocity);  // New endpoint for velocity limits
  server.on("/set_wait_time", HTTP_GET, handleSetWaitTime);
  // Add this line with the other server.on calls in setup() (around line 690)
server.on("/toggle_pid_control", HTTP_GET, handleTogglePidControl);

  
  // NEW: Pump control endpoints
  server.on("/pump_ascend", HTTP_GET, handlePumpAscend);
  server.on("/pump_descend", HTTP_GET, handlePumpDescend);
  server.on("/pump_stop", HTTP_GET, handlePumpStop);
  
  server.begin();
  Serial.println("HTTP server started on port 80");

  // Initialize the depth sensor
  Wire.begin();
  sensor.setModel(MS5837::MS5837_02BA);
  if (!sensor.init()) {
    Serial.println("MS5837 sensor init failed!");
  }
  sensor.setFluidDensity(1029);

  // Set initial wifiFlag based on current RSSI
  if (WiFi.status() == WL_CONNECTED) {
    long rssi = WiFi.RSSI();
    wifiFlag = (rssi >= RSSI_THRESHOLD);
  }

  // Create FreeRTOS tasks on different cores
  xTaskCreatePinnedToCore(
    TaskWifiServer,
    "TaskWifiServer",
    4096,
    NULL,
    1,
    NULL,
    0
  );

  xTaskCreatePinnedToCore(
    TaskSensorAndSending,
    "TaskSensorAndSending",
    8192,
    NULL,
    1,
    NULL,
    1
  );
}

void loop() {
  // Nothing here – all work is done in FreeRTOS tasks
  delay(500);
}