#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <cppQueue.h>
#include <Wire.h>
#include <MS5837.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>

// -------------------- CONFIGURATION --------------------
#define WIFI_SSID           "NR-3"
#define WIFI_PASSWORD       "Radhi02@Nagi22"
int COMPANY_NUMBER = 6969;

// RSSI THRESHOLD (dBm)
#define RSSI_THRESHOLD      -70

// NeoPixel on GPIO0, powering from GPIO2
#define NEOPIXEL_DATA_PIN   0
#define NEOPIXEL_POWER_PIN  2
#define NUM_PIXELS          1

// Data capture intervals (milliseconds)
int NORMAL_READ_INTERVAL = 2000;
int VELOCITY_READ_INTERVAL = 20;  // faster rate for velocity testing

// Add these variables to your global declarations
unsigned long SLOW_SEND_INTERVAL = 2500;  // 2.5 seconds
unsigned long FAST_SEND_INTERVAL = 250;   // 0.25 seconds
unsigned long currentSendInterval = SLOW_SEND_INTERVAL;
unsigned long lastSuccessfulSend = 0;
bool lastSendSuccessful = false;

// Batch send size
#define SEND_BATCH_SIZE     5

// Pump control pins
#define PUMP_DESC_PIN       27   // fill ballast
#define PUMP_ASC_PIN        12   // empty ballast

// PID control
float TARGET_DEPTH = 2.625;      // Middle of range (2.5–2.75m)
float DEPTH_TOLERANCE = 0.125;  // ±0.125m

float Kp = 1.0;
float Ki = 0.02;
float Kd = 0.03;

float integral = 0.0;
float previousError = 0.0;
unsigned long lastPidTime = 0;
int pidDeadband = 5;  // Below this absolute value, the pump stays off

unsigned long routineWaitTime = 45000; // 45 seconds
int pidOutput = 0;

volatile bool pidControlActive = false;

// Routine state
enum RoutineState { R_IDLE, R_DESCENDING, R_WAITING, R_ASCENDING };
volatile bool routineActive = false;
volatile RoutineState routineState = R_IDLE;
unsigned long routineWaitStart = 0;

// Velocity limits
float maxDescentVelocity = 0.18;  // m/s
float maxAscentVelocity  = 0.1;   // m/s

unsigned long previousTime  = 0;
float        previousDepth = 0.0;

volatile bool wifiFlag   = false;
volatile bool hasStarted = false;
unsigned long currentReadInterval = NORMAL_READ_INTERVAL;

// Measurement queue
struct Measurement {
  unsigned long timeSinceStart;
  float         depth;
  float         pressure;
  int           companyNum;
  float         velocity;
  int           pidOutput;
  float         pidError;
  String        pumpStatus;
};

cppQueue measurementQueue(sizeof(Measurement), 800, FIFO, false);

WebServer server(80);
HTTPClient http;
MS5837 sensor;
Adafruit_NeoPixel strip(NUM_PIXELS, NEOPIXEL_DATA_PIN, NEO_GRB + NEO_KHZ800);

unsigned long startTime    = 0;
float        initialDepth  = 0.0;
String       laptopIpAddress;

// Helper: NeoPixel
void setStripColor(uint8_t r, uint8_t g, uint8_t b) {
  strip.setPixelColor(0, strip.Color(r, g, b));
  strip.show();
}

// Replace your current calculatePid function with this corrected version
int calculatePid(float currentDepth, float* errorOut) {
  unsigned long now = millis();
  float deltaTime = (now - lastPidTime) / 1000.0;
  
  // Better initialization check
  if (deltaTime < 0.01 || lastPidTime == 0) {
    lastPidTime = now;
    // Calculate and return error even on first call
    float error = TARGET_DEPTH - currentDepth;
    *errorOut = error;
    Serial.printf("PID INIT: Target=%.3f, Current=%.3f, Error=%.3f\n", 
                  TARGET_DEPTH, currentDepth, error);
    return 0;
  }
  
  float error = TARGET_DEPTH - currentDepth;
  *errorOut = error;
  
  // Debug output to verify error calculation
  Serial.printf("PID DEBUG: Target=%.3f, Current=%.3f, Error=%.3f\n", 
                TARGET_DEPTH, currentDepth, error);

  integral += error * deltaTime;
  integral = constrain(integral, -20, 20);

  float derivative = (error - previousError) / deltaTime;
  int output = int(Kp * error + Ki * integral + Kd * derivative);
  pidOutput = constrain(output, -100, 100);

  previousError = error;
  lastPidTime = now;
  
  // Log PID components for debugging
  Serial.printf("PID COMPONENTS: P=%.2f, I=%.2f, D=%.2f, Output=%d\n",
                Kp * error, Ki * integral, Kd * derivative, pidOutput);
                
  return pidOutput;
}

// Pump helpers
void pumpDescend() { digitalWrite(PUMP_DESC_PIN, HIGH);  digitalWrite(PUMP_ASC_PIN, LOW); }
void pumpAscend()  { digitalWrite(PUMP_DESC_PIN, LOW);   digitalWrite(PUMP_ASC_PIN, HIGH); }
void pumpOff()     { digitalWrite(PUMP_DESC_PIN, LOW);   digitalWrite(PUMP_ASC_PIN, LOW); }

// Apply PID to pump
// Replace your applyPidToPump function
void applyPidToPump(int output, String* status) {
  if (output > pidDeadband) {
    pumpDescend();
    *status = "Descending";
    Serial.printf("PID: Descending (output: %d)\n", output);
  } else if (output < -pidDeadband) {
    pumpAscend();
    *status = "Ascending";
    Serial.printf("PID: Ascending (output: %d)\n", output);
  } else {
    pumpOff();
    *status = "Off";
    Serial.printf("PID: Holding position (output: %d within deadband ±%d)\n", 
                 output, pidDeadband);
  }
}


// Send measurements
bool sendMeasurements(Measurement* m, int count) {
  if (!wifiFlag || laptopIpAddress.isEmpty() || count <= 0) return false;

  DynamicJsonDocument doc(2048);
  JsonArray arr = doc.createNestedArray("data");
  for (int i = 0; i < count; i++) {
    JsonObject obj = arr.createNestedObject();
    obj["time"]       = m[i].timeSinceStart / 1000.0;
    obj["depth"]      = m[i].depth;
    obj["pressure"]   = m[i].pressure;
    obj["company"]    = m[i].companyNum;
    obj["velocity"]   = m[i].velocity;
    obj["pid_output"] = m[i].pidOutput;
    obj["pid_error"]  = m[i].pidError;
    obj["pump_status"] = m[i].pumpStatus;
  }
  String payload;
  serializeJson(doc, payload);

  http.begin("http://" + laptopIpAddress + ":8000/depth");
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(payload);
  http.end();
  return (code == 200);
}

// Helper function to convert routine state to string
String routineStateToString(RoutineState state) {
  switch (state) {
    case R_IDLE: return "idle";
    case R_DESCENDING: return "descending";
    case R_WAITING: return "waiting";
    case R_ASCENDING: return "ascending";
    default: return "unknown";
  }
}

// HTTP handlers
void handleSetCompanyNumber() {
  if (!server.hasArg("value")) {
    server.send(400, "text/plain", "Missing 'value' parameter");
    return;
  }
  
  int value = server.arg("value").toInt();
  if (value <= 0) {
    server.send(400, "text/plain", "Company number must be a positive integer");
    return;
  }
  
  COMPANY_NUMBER = value;
  String resp = "Company number updated to " + String(COMPANY_NUMBER);
  server.send(200, "text/plain", resp);
  Serial.println(resp);
}
void handleSetPidDeadband() {
  if (!server.hasArg("value")) {
    server.send(400, "text/plain", "Missing 'value' parameter");
    return;
  }
  int val = server.arg("value").toInt();
  if (val < 0 || val > 50) {
    server.send(400, "text/plain", "Deadband must be 0-50");
    return;
  }
  pidDeadband = val;
  String resp = "PID deadband updated to " + String(pidDeadband);
  server.send(200, "text/plain", resp);
  Serial.println(resp);
}
void handleSetDepthTolerance() {
  if (!server.hasArg("tolerance")) {
    server.send(400, "text/plain", "Missing 'tolerance' parameter");
    return;
  }
  float t = server.arg("tolerance").toFloat();
  if (t <= 0 || t >= 1.0) {
    server.send(400, "text/plain", "Tolerance must be between 0 and 1.0m");
    return;
  }
  DEPTH_TOLERANCE = t;
  String resp = "Depth tolerance updated to ±" + String(DEPTH_TOLERANCE) + "m";
  server.send(200, "text/plain", resp);
  Serial.println(resp);
}

void handleSetReadIntervals() {
  bool normalChanged = false;
  bool velocityChanged = false;
  
  if (server.hasArg("normal")) {
    int interval = server.arg("normal").toInt();
    if (interval >= 100 && interval <= 10000) {
      NORMAL_READ_INTERVAL = interval;
      normalChanged = true;
    }
  }
  
  if (server.hasArg("velocity")) {
    int interval = server.arg("velocity").toInt();
    if (interval >= 10 && interval <= 1000) {
      VELOCITY_READ_INTERVAL = interval;
      velocityChanged = true;
    }
  }
  
  // Update the current interval if we're not in velocity mode
  if (normalChanged && currentReadInterval != VELOCITY_READ_INTERVAL) {
    currentReadInterval = NORMAL_READ_INTERVAL;
  }
  
  String resp = "Read intervals updated: ";
  if (normalChanged) resp += "normal=" + String(NORMAL_READ_INTERVAL) + "ms ";
  if (velocityChanged) resp += "velocity=" + String(VELOCITY_READ_INTERVAL) + "ms";
  if (!normalChanged && !velocityChanged) resp = "No valid intervals provided";
  
  server.send(200, "text/plain", resp);
  Serial.println(resp);
}
void handleStatus() {
  DynamicJsonDocument doc(1024);  // Increased size to accommodate all data
  
  // System status
  doc["started"] = hasStarted;
  doc["uptime_seconds"] = millis() / 1000;
  doc["free_heap"] = ESP.getFreeHeap();
  doc["company_number"] = COMPANY_NUMBER;
  
  // WiFi info
  JsonObject wifi = doc.createNestedObject("wifi");
  wifi["rssi"] = WiFi.RSSI();
  wifi["connected"] = (WiFi.status() == WL_CONNECTED);
  wifi["good_signal"] = wifiFlag;
  wifi["ip"] = WiFi.localIP().toString();
  
  // Queue status
  JsonObject queue = doc.createNestedObject("queue");
  queue["current_size"] = measurementQueue.getCount();
  queue["capacity"] = 800;
  queue["percent_full"] = (measurementQueue.getCount() * 100) / 800;
  queue["read_interval_ms"] = currentReadInterval;
  queue["velocity_interval_ms"] = VELOCITY_READ_INTERVAL;  // Add this line
  
  // Depth info
  JsonObject depth = doc.createNestedObject("depth");
  depth["current"] = sensor.depth() - initialDepth;
  depth["target"] = TARGET_DEPTH;
  depth["tolerance"] = DEPTH_TOLERANCE;
  depth["pressure"] = sensor.pressure();
  
  // Velocity info
  JsonObject velocity = doc.createNestedObject("velocity");
  float currentVelocity = 0;
  if (previousTime > 0) {
    unsigned long dt_ms = millis() - previousTime;
    if (dt_ms > 0) {
      float dt = dt_ms / 1000.0;
      currentVelocity = (sensor.depth() - initialDepth - previousDepth) / dt;
    }
  }
  velocity["current"] = currentVelocity;
  velocity["max_descent"] = maxDescentVelocity;
  velocity["max_ascent"] = maxAscentVelocity;
  
  // PID parameters
  JsonObject pid = doc.createNestedObject("pid");
  pid["active"] = pidControlActive;
  pid["kp"] = Kp;
  pid["ki"] = Ki;
  pid["kd"] = Kd;
  pid["deadband"] = pidDeadband;  // Add this line to include the deadband value
  pid["last_output"] = pidOutput;
  pid["last_error"] = previousError;
  pid["integral"] = integral;
  
  // Routine status
  JsonObject routine = doc.createNestedObject("routine");
  routine["active"] = routineActive;
  routine["state"] = routineStateToString(routineState);
  routine["wait_time_seconds"] = routineWaitTime / 1000;
  
  if (routineActive && routineState == R_WAITING) {
    unsigned long elapsedWait = millis() - routineWaitStart;
    routine["wait_elapsed_seconds"] = elapsedWait / 1000;
    routine["wait_remaining_seconds"] = (routineWaitTime > elapsedWait) ? 
                                        (routineWaitTime - elapsedWait) / 1000 : 0;
  }
  
  // Pump status
  JsonObject pump = doc.createNestedObject("pump");
  bool pumpDescActive = digitalRead(PUMP_DESC_PIN) == HIGH;
  bool pumpAscActive = digitalRead(PUMP_ASC_PIN) == HIGH;
  
  if (pumpDescActive && !pumpAscActive) {
    pump["state"] = "descending";
  } else if (!pumpDescActive && pumpAscActive) {
    pump["state"] = "ascending";
  } else {
    pump["state"] = "off";
  }
  
  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}


void handleSetTargetDepth() {
  if (!server.hasArg("depth")) {
    server.send(400, "text/plain", "Missing 'depth' parameter");
    return;
  }
  float d = server.arg("depth").toFloat();
  if (d <= 0 || d >= 10) {
    server.send(400, "text/plain", "Depth must be 0–10m");
    return;
  }
  TARGET_DEPTH = d;
  String resp = "Target depth updated to " + String(TARGET_DEPTH) + "m";
  server.send(200, "text/plain", resp);
  Serial.println(resp);
}

void handleSetPid() {
  if (server.hasArg("kp")) Kp = server.arg("kp").toFloat();
  if (server.hasArg("ki")) Ki = server.arg("ki").toFloat();
  if (server.hasArg("kd")) Kd = server.arg("kd").toFloat();
  String resp = "PID updated: Kp=" + String(Kp) + ", Ki=" + String(Ki) + ", Kd=" + String(Kd);
  server.send(200, "text/plain", resp);
  Serial.println(resp);
}

void handleSetWaitTime() {
  if (!server.hasArg("seconds")) {
    server.send(400, "text/plain", "Missing 'seconds'");
    return;
  }
  int s = server.arg("seconds").toInt();
  if (s <= 0) {
    server.send(400, "text/plain", "Seconds must be positive");
    return;
  }
  routineWaitTime = (unsigned long)s * 1000;
  String resp = "Wait time updated to " + String(s) + "s";
  server.send(200, "text/plain", resp);
  Serial.println(resp);
}

void handleStartSignal() {
  if (!server.hasArg("ip_address")) {
    server.send(400, "text/plain", "Missing ip_address");
    return;
  }
  laptopIpAddress = server.arg("ip_address");
  if (!hasStarted) {
    hasStarted      = true;
    pidControlActive = false;
    startTime       = millis();
    sensor.read();
    initialDepth    = sensor.depth();
    previousTime    = 0;
    previousDepth   = 0;
    String resp = "Started posting to " + laptopIpAddress + ":8000/depth";
    server.send(200, "text/plain", resp);
  } else {
    server.send(200, "text/plain", "Already started");
  }
}

void handleStopSignal() {
  hasStarted = false;
  pidControlActive = false;
  routineActive    = false;
  measurementQueue.flush();
  currentReadInterval = NORMAL_READ_INTERVAL;
  routineState = R_IDLE;
  server.send(200, "text/plain", "Float stopped and reset");
}

void handleStartVelocity() {
  if (!hasStarted) {
    server.send(400, "text/plain", "Start float first");
    return;
  }
  currentReadInterval = VELOCITY_READ_INTERVAL;
  server.send(200, "text/plain", "Velocity testing started");
}

void handleStopVelocity() {
  if (!hasStarted) {
    server.send(400, "text/plain", "Start float first");
    return;
  }
  currentReadInterval = NORMAL_READ_INTERVAL;
  server.send(200, "text/plain", "Velocity testing stopped");
}

void handleSetVelocity() {
  if (server.hasArg("descent")) maxDescentVelocity = server.arg("descent").toFloat();
  if (server.hasArg("ascent"))  maxAscentVelocity  = server.arg("ascent").toFloat();
  String resp = "Velocity limits: descent=" + String(maxDescentVelocity) + ", ascent=" + String(maxAscentVelocity);
  server.send(200, "text/plain", resp);
  Serial.println(resp);
}

void handleStartRoutine() {
  if (!hasStarted) {
    server.send(400, "text/plain", "Start float first");
    return;
  }
  if (!routineActive) {
    routineActive  = true;
    routineState   = R_DESCENDING;
    previousTime   = 0;
    previousDepth  = 0;
    integral       = 0;
    previousError  = 0;
    lastPidTime    = 0;
    server.send(200, "text/plain", "Routine started: Descending");
    Serial.println("Routine started: Descending");
  } else {
    server.send(200, "text/plain", "Routine already active");
  }
}

void handlePumpAscend()  { pumpAscend();  server.send(200, "text/plain", "Pump ascending"); }
void handlePumpDescend() { pumpDescend(); server.send(200, "text/plain", "Pump descending"); }
void handlePumpStop()   { pumpOff();     server.send(200, "text/plain", "Pump stopped"); }

// Replace your handleTogglePidControl function with this enhanced version
void handleTogglePidControl() {
  pidControlActive = !pidControlActive;
  
  if (pidControlActive) {
    // Reset PID state variables when enabling PID
    integral = 0.0;
    previousError = 0.0;
    lastPidTime = 0;  // Force recalculation on next cycle
    
    // Check if target depth is reasonable
    float currentDepth = sensor.depth() - initialDepth;
    Serial.printf("PID ENABLED: Current depth=%.3f, Target depth=%.3f\n", 
                 currentDepth, TARGET_DEPTH);
                 
    // Initial calculation to give immediate feedback
    float pidErr;
    pidOutput = calculatePid(currentDepth, &pidErr);
    
    String status;
    applyPidToPump(pidOutput, &status);
    Serial.printf("Initial PID action: %s (output=%d)\n", status.c_str(), pidOutput);
  } else {
    pumpOff();
  }
  
  String resp = String("PID control is now ") + (pidControlActive ? "enabled" : "disabled");
  server.send(200, "text/plain", resp);
  Serial.println(resp);
}

// Task on core 0: WiFi & HTTP server
void TaskWifiServer(void*) {
  for (;;) {
    server.handleClient();
    wifiFlag = (WiFi.status() == WL_CONNECTED && WiFi.RSSI() >= RSSI_THRESHOLD);
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }
}

// Task on core 1: Sensor, routine, queue, send
void TaskSensorAndSending(void*) {
  unsigned long lastRead = 0;
  float currentVelocity;
  String pumpStatus;
  float pidErr;

  for (;;) {
    unsigned long now = millis();

    // Replace with this code:
    sensor.read();
    float sensorDepth = sensor.depth();

    // Validate sensor reading
    if (isnan(sensorDepth) || sensorDepth < -10 || sensorDepth > 100) {
      Serial.println("WARNING: Invalid sensor reading detected!");
      // Skip this reading, don't update depth
    } else {
      float depth = sensorDepth - initialDepth;
      if (previousTime > 0) {
        float dt = (now - previousTime) / 1000.0;
        currentVelocity = (depth - previousDepth) / dt;
      }
      previousTime  = now;
      previousDepth = depth;

      if (hasStarted) {
        // Routine state machine
        if (routineActive) {
          switch (routineState) {
            case R_DESCENDING:
              if (currentVelocity > maxDescentVelocity) {
                pumpOff();
                pumpStatus = "Routine-LimitD";
                Serial.printf("ROUTINE: Descent velocity %.3f > %.3f\n", currentVelocity, maxDescentVelocity);
              } else {
                pumpDescend();
                pumpStatus = "Routine-Descend";
                if (depth >= TARGET_DEPTH) {
                  pumpOff();
                  routineState = R_WAITING;
                  routineWaitStart = now;
                  Serial.println("Routine: Target depth reached");
                }
              }
              break;

            case R_WAITING:
              if (now - routineWaitStart >= routineWaitTime) {
                pumpAscend();
                routineState = R_ASCENDING;
                integral = previousError = lastPidTime = 0;
                pumpStatus = "Routine-Ascend";
                Serial.println("Routine: Ascending initiated");
              } else {
                // Make sure we're using the current depth
                float currentDepth = depth;
                pidOutput = calculatePid(currentDepth, &pidErr);
                
                // Debug output to track PID behavior
                Serial.printf("ROUTINE WAIT: Depth=%.3f, Target=%.3f, Error=%.3f, PID=%d\n", 
                            currentDepth, TARGET_DEPTH, pidErr, pidOutput);
                
                applyPidToPump(pidOutput, &pumpStatus);
                
                // Add more detailed warnings
                if (depth < TARGET_DEPTH - DEPTH_TOLERANCE) {
                  Serial.printf("WARNING: Too shallow (%.3f < %.3f)\n", 
                              depth, TARGET_DEPTH - DEPTH_TOLERANCE);
                }
                if (depth > TARGET_DEPTH + DEPTH_TOLERANCE) {
                  Serial.printf("WARNING: Too deep (%.3f > %.3f)\n", 
                              depth, TARGET_DEPTH + DEPTH_TOLERANCE);
                }
              }
              break;

            case R_ASCENDING:
              if (currentVelocity < -maxAscentVelocity) {
                pumpOff();
                pumpStatus = "Routine-LimitA";
                Serial.printf("ROUTINE: Ascent velocity %.3f > %.3f\n", -currentVelocity, maxAscentVelocity);
              } else {
                pumpAscend();
                pumpStatus = "Routine-Ascend";
                if (depth <= 0.5) {
                  pumpOff();
                  routineActive = false;
                  routineState  = R_IDLE;
                  pumpStatus    = "Complete";
                  Serial.println("Routine: Complete");
                }
              }
              break;

            default:
              pumpStatus = "Routine-Idle";
              break;
          }
        } else if (pidControlActive) {
          pidOutput = calculatePid(depth, &pidErr);
          applyPidToPump(pidOutput, &pumpStatus);
        }

        // Data capture
        if (now - lastRead >= currentReadInterval) {
          lastRead = now;
          float pressure = sensor.pressure();
          unsigned long elapsed = now - startTime;

          Measurement m = { elapsed, depth, pressure, COMPANY_NUMBER, currentVelocity, pidOutput, pidErr, pumpStatus };
          if (!measurementQueue.push(&m)) Serial.println("Queue full");
          else Serial.printf("DATA t=%lu d=%.3f v=%.3f p=%d err=%.3f st=%s\n", elapsed, depth, currentVelocity, pidOutput, pidErr, pumpStatus.c_str());
        }

      } else {
        setStripColor(255, 0, 0); // RED if not started
      }
    }

    // Send
    if (wifiFlag && !measurementQueue.isEmpty()) {
      static unsigned long lastSendAttempt = 0;
      unsigned long now = millis();
      
      // Determine if it's time to attempt sending
      if (now - lastSendAttempt >= currentSendInterval) {
        lastSendAttempt = now;
        
        // If in velocity test mode, always send at fast rate
        if (currentReadInterval == VELOCITY_READ_INTERVAL) {
          currentSendInterval = FAST_SEND_INTERVAL;
        } 
        // Otherwise use adaptive rate based on success
        else {
          // If last send was successful and recent, use fast rate
          if (lastSendSuccessful && (now - lastSuccessfulSend < 5000)) {
            currentSendInterval = FAST_SEND_INTERVAL;
          } else {
            currentSendInterval = SLOW_SEND_INTERVAL;
          }
        }
        
        // Attempt to send a batch
        Measurement batch[SEND_BATCH_SIZE];
        int count = 0;
        while (count < SEND_BATCH_SIZE && measurementQueue.peek(&batch[count])) {
          measurementQueue.drop();
          count++;
        }
        
        if (count > 0) {
          if (sendMeasurements(batch, count)) {
            setStripColor(0, 0, 255); // BLUE on successful send
            lastSendSuccessful = true;
            lastSuccessfulSend = now;
            Serial.printf("Sent %d measurements (queue: %d)\n", 
                        count, measurementQueue.getCount());
          } else {
            lastSendSuccessful = false;
            Serial.printf("Send failed, requeueing (retry in %.1f seconds)\n", 
                        currentSendInterval/1000.0);
                        
            // Requeue in reverse order to maintain original sequence
            bool lostData = false;
            for (int i = count-1; i >= 0; i--) {
              if (!measurementQueue.push(&batch[i])) {
                Serial.printf("WARNING: Lost data point at t=%lu\n", batch[i].timeSinceStart);
                lostData = true;
              }
            }
            if (lostData) {
              // Flash RED to indicate data loss
              setStripColor(255, 0, 0);
              delay(50);
            }
          }
        }
      }
    }

    // LED status
    if (!wifiFlag) {
      setStripColor(255, 0, 0); // RED if WiFi poor
    } 
    else if (pidControlActive || (routineActive && routineState == R_WAITING)) {
      setStripColor(255, 165, 0); // ORANGE when PID is running
    }
    else if (measurementQueue.isEmpty()) {
      setStripColor(0, 255, 0);   // GREEN if queue empty
    }
    else {
      setStripColor(255, 255, 0); // YELLOW if queue has data
    }

    vTaskDelay(50 / portTICK_PERIOD_MS);
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(NEOPIXEL_POWER_PIN, OUTPUT);
  digitalWrite(NEOPIXEL_POWER_PIN, HIGH);
  strip.begin();
  strip.setBrightness(50);
  setStripColor(255, 0, 0);

  pinMode(PUMP_DESC_PIN, OUTPUT);
  pinMode(PUMP_ASC_PIN, OUTPUT);
  pumpOff();
  
  // Initialize WiFi with timeout
  unsigned long wifiStartTime = millis();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
    if (millis() - wifiStartTime > 30000) { // 30 second timeout
      Serial.println("\nWiFi connection failed! Restarting...");
      ESP.restart();
    }
  }
  Serial.println("\nWiFi connected, IP: " + WiFi.localIP());

  // HTTP routes
  server.on("/start_signal",        HTTP_GET, handleStartSignal);
  server.on("/stop_signal",         HTTP_GET, handleStopSignal);
  server.on("/start_velocity",      HTTP_GET, handleStartVelocity);
  server.on("/stop_velocity",       HTTP_GET, handleStopVelocity);
  server.on("/set_velocity",        HTTP_GET, handleSetVelocity);
  server.on("/start_routine",       HTTP_GET, handleStartRoutine);
  server.on("/set_pid",             HTTP_GET, handleSetPid);
  server.on("/set_wait_time",       HTTP_GET, handleSetWaitTime);
  server.on("/toggle_pid_control",  HTTP_GET, handleTogglePidControl);
  server.on("/set_target_depth",    HTTP_GET, handleSetTargetDepth);
  server.on("/pump_ascend",         HTTP_GET, handlePumpAscend);
  server.on("/pump_descend",        HTTP_GET, handlePumpDescend);
  server.on("/pump_stop",           HTTP_GET, handlePumpStop);
  server.on("/status",              HTTP_GET, handleStatus);
  server.on("/set_depth_tolerance", HTTP_GET, handleSetDepthTolerance);
  server.on("/set_read_intervals",  HTTP_GET, handleSetReadIntervals);
  server.on("/set_pid_deadband", HTTP_GET, handleSetPidDeadband);
  server.on("/set_company_number", HTTP_GET, handleSetCompanyNumber);
  server.begin();
  Serial.println("HTTP server started");
  Serial.println("\nWiFi connected!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  Wire.begin();
  sensor.setModel(MS5837::MS5837_02BA);
  if (!sensor.init()) Serial.println("Sensor init failed!");
  sensor.setFluidDensity(1029);

  wifiFlag = (WiFi.status() == WL_CONNECTED && WiFi.RSSI() >= RSSI_THRESHOLD);

  xTaskCreatePinnedToCore(TaskWifiServer,     "TaskWifiServer",     4096, NULL, 1, NULL, 0);
  xTaskCreatePinnedToCore(TaskSensorAndSending,"TaskSensorAndSending",8192, NULL, 1, NULL, 1);
}

void loop() {
  // All work is done in tasks
  delay(500);
}
