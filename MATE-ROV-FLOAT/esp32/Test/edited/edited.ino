#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <cppQueue.h>
#include <Wire.h>
#include <MS5837.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>

// -------------------- CONFIGURATION --------------------
#define WIFI_SSID "SBRT"
#define WIFI_PASSWORD "Robotic$3"
int COMPANY_NUMBER = 6969;

// RSSI THRESHOLD (dBm)
#define RSSI_THRESHOLD -70

// NeoPixel on GPIO0, powering from GPIO2
#define NEOPIXEL_DATA_PIN 0
#define NEOPIXEL_POWER_PIN 2
#define NUM_PIXELS 1

// Data capture and send intervals (milliseconds)
int NORMAL_READ_INTERVAL = 4000; // 4 seconds
unsigned long SEND_INTERVAL = 5000; // 5 seconds
unsigned long lastSuccessfulSend = 0;
bool lastSendSuccessful = false;

// Batch send size
#define SEND_BATCH_SIZE 1 // Send one packet at a time

// Pump control pins
#define PUMP_DESC_PIN 27 // fill ballast
#define PUMP_ASC_PIN 12  // empty ballast

// Routine control
float TARGET_DEPTH = 2.5;      // Target depth for routine, e.g., 2.5m
const float ROUTINE_DEPTH_TOLERANCE = 0.5; // ±0.5m for data collection at target
const float ROUTINE_TARGET_APPROACH_THRESHOLD = 0.5; // Start fine control 0.5m before target
unsigned long routineWaitTime = 80000; // Max time to spend in data collection state (80 seconds)

// Routine state
enum RoutineState { R_IDLE, R_DESCENDING, R_COLLECTING_DATA, R_ASCENDING, R_EMERGENCY_ASCENT, R_NEUTRALIZING_BALLAST }; // Added R_NEUTRALIZING_BALLAST
volatile bool routineActive = false;
volatile RoutineState routineState = R_IDLE;
unsigned long routineStateStartTime = 0; // Time when current routine state started
int packetsCollectedAtTarget = 0;
const int PACKETS_AT_TARGET_GOAL = 10;

// Velocity limits
float maxDescentVelocity = 0.1; // m/s
float maxAscentVelocity = 0.1;  // m/s (positive value for magnitude)

// Descent Pump Safety Timer
unsigned long descentPumpActiveStartTime = 0; // Time when descent pump was last activated in current segment
unsigned long totalDescentPumpRunTimeThisRoutine = 0; // Cumulative run time for this routine's descent phase
const unsigned long MAX_TOTAL_DESCENT_PUMP_TIME = 20000; // 20 seconds MAX cumulative descent pump ON time per routine descent
const unsigned long DESCENT_TIMER_COMPENSATION_OFFSET_MS = 50; // Compensation for accumulation characteristic (tied to TaskSensorAndSending delay)

// Ballast Neutralization Control
volatile bool stopSignalPending = false; // Flag for stop signal processing in the main task
unsigned long ascentNeutralizationTargetDuration = 0; // How long to run ascend pump for neutralization
unsigned long neutralizationStateStartTime = 0;     // Start time of the neutralization phase

unsigned long previousTime = 0;
float previousDepth = 0.0;

volatile bool wifiFlag = false;
volatile bool hasStarted = false;
unsigned long currentReadInterval = NORMAL_READ_INTERVAL; 

// Measurement queue
struct Measurement {
    unsigned long timeSinceStart;
    float depth;
    float pressure;
    int companyNum;
    float velocity;
    String pumpStatus;
};

cppQueue measurementQueue(sizeof(Measurement), 800, FIFO, false);

WebServer server(80);
MS5837 sensor;
Adafruit_NeoPixel strip(NUM_PIXELS, NEOPIXEL_DATA_PIN, NEO_GRB + NEO_KHZ800);

unsigned long startTime = 0;
float initialDepth = 0.0;
String laptopIpAddress;

// LED State Variables
unsigned long lastBlinkTime = 0;
bool blinkState = false;
unsigned long ledRoutineCompleteStart = 0;
bool routineJustCompletedLedActive = false;
#define LED_BLINK_INTERVAL_NOT_STARTED 1000 
#define LED_BLINK_INTERVAL_ROUTINE 2000     
#define LED_ROUTINE_COMPLETE_DURATION 5000  

// WiFi Reconnection Logic
unsigned long lastWifiReconnectAttempt = 0;
const unsigned long WIFI_RECONNECT_INTERVAL = 10000; // 10 seconds

// Helper: NeoPixel
void setStripColor(uint8_t r, uint8_t g, uint8_t b) {
    strip.setPixelColor(0, strip.Color(r, g, b));
    strip.show();
}

// Pump helpers
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

// Send measurements
bool sendMeasurements(Measurement *m, int count) {
    if (!hasStarted || !wifiFlag || laptopIpAddress.isEmpty() || count <= 0) {
        return false;
    }

    DynamicJsonDocument doc(1024 + count * 256); 
    JsonArray arr = doc.createNestedArray("data");
    for (int i = 0; i < count; i++) {
        JsonObject obj = arr.createNestedObject();
        obj["time"] = m[i].timeSinceStart / 1000.0;
        obj["depth"] = m[i].depth;
        obj["pressure"] = m[i].pressure;
        obj["company"] = m[i].companyNum;
        obj["velocity"] = m[i].velocity;
        obj["pump_status"] = m[i].pumpStatus;
    }
    String payload;
    serializeJson(doc, payload);

    HTTPClient localHttp; 
    localHttp.begin("http://" + laptopIpAddress + ":8000/depth");
    localHttp.addHeader("Content-Type", "application/json");
    localHttp.setTimeout(4000); 
    int code = localHttp.POST(payload);
    localHttp.end();
    return (code == 200);
}

String routineStateToString(RoutineState state) {
    switch (state) {
    case R_IDLE: return "idle";
    case R_DESCENDING: return "descending";
    case R_COLLECTING_DATA: return "collecting_data_at_target";
    case R_ASCENDING: return "ascending";
    case R_EMERGENCY_ASCENT: return "emergency_ascent";
    case R_NEUTRALIZING_BALLAST: return "neutralizing_ballast"; // Added
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

void handleStatus() {
    DynamicJsonDocument doc(1024);

    doc["started"] = hasStarted;
    doc["uptime_seconds"] = millis() / 1000;
    doc["free_heap"] = ESP.getFreeHeap();
    doc["company_number"] = COMPANY_NUMBER;

    JsonObject wifi_status = doc.createNestedObject("wifi"); // Renamed to avoid conflict
    wifi_status["rssi"] = WiFi.RSSI();
    wifi_status["connected"] = (WiFi.status() == WL_CONNECTED);
    wifi_status["good_signal"] = wifiFlag;
    wifi_status["ip"] = WiFi.localIP().toString();

    JsonObject queue_info = doc.createNestedObject("queue"); 
    queue_info["current_size"] = measurementQueue.getCount();
    queue_info["capacity"] = 800; 
    queue_info["percent_full"] = (measurementQueue.getCount() * 100) / 800;
    queue_info["read_interval_ms"] = currentReadInterval;
    queue_info["send_interval_ms"] = SEND_INTERVAL;


    JsonObject depth_info = doc.createNestedObject("depth");
    float currentDepthVal = NAN; 
    float rawDepthStatus = sensor.depth(); 
    if(hasStarted && !isnan(rawDepthStatus)) currentDepthVal = rawDepthStatus - initialDepth; 
    else if (!isnan(rawDepthStatus)) currentDepthVal = rawDepthStatus; 
    
    depth_info["current"] = currentDepthVal;
    depth_info["target"] = TARGET_DEPTH;
    depth_info["target_tolerance"] = ROUTINE_DEPTH_TOLERANCE;
    depth_info["pressure"] = sensor.pressure(); 
    
    JsonObject velocity_info = doc.createNestedObject("velocity");
    float tempCurrentVelocity = 0;
    if (previousTime > 0 && hasStarted && !isnan(currentDepthVal)) {
        unsigned long dt_ms = millis() - previousTime; 
        if (dt_ms > 0) {
            float dt_s = dt_ms / 1000.0;
            tempCurrentVelocity = (currentDepthVal - previousDepth) / dt_s; 
        }
    }
    velocity_info["current"] = tempCurrentVelocity; 
    velocity_info["max_descent_config"] = maxDescentVelocity;
    velocity_info["max_ascent_config"] = maxAscentVelocity;

    JsonObject routine_info = doc.createNestedObject("routine"); 
    routine_info["active"] = routineActive;
    routine_info["state"] = routineStateToString(routineState);
    routine_info["wait_time_seconds_config"] = routineWaitTime / 1000;
    routine_info["packets_collected_at_target"] = packetsCollectedAtTarget;
    routine_info["packets_goal_at_target"] = PACKETS_AT_TARGET_GOAL;

    if (routineActive && routineState == R_COLLECTING_DATA) {
        unsigned long elapsedWait = millis() - routineStateStartTime;
        routine_info["time_in_collection_state_seconds"] = elapsedWait / 1000;
        routine_info["collection_timeout_remaining_seconds"] = (routineWaitTime > elapsedWait) ? (routineWaitTime - elapsedWait) / 1000 : 0;
    }

    JsonObject pump_info = doc.createNestedObject("pump"); 
    bool pumpDescActive = digitalRead(PUMP_DESC_PIN) == HIGH;
    bool pumpAscActive = digitalRead(PUMP_ASC_PIN) == HIGH;
    if (pumpDescActive) pump_info["state"] = "descending";
    else if (pumpAscActive) pump_info["state"] = "ascending";
    else pump_info["state"] = "off";

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
    if (d < 0 || d > 10) { 
        server.send(400, "text/plain", "Depth must be 0–10m");
        return;
    }
    TARGET_DEPTH = d;
    String resp = "Target depth updated to " + String(TARGET_DEPTH) + "m";
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
    String resp = "Routine wait time (at target) updated to " + String(s) + "s";
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
        hasStarted = true;
        startTime = millis();
        sensor.read(); 
        initialDepth = sensor.depth();
        if (isnan(initialDepth)) {
            Serial.println("ERROR: Failed to get valid initial depth reading on start! Restarting float.");
            server.send(500, "text/plain", "Error: Failed to read initial depth. Restarting.");
            delay(1000);
            ESP.restart();
            return;
        }
        previousTime = 0;      
        previousDepth = 0;     
        measurementQueue.flush(); 
        routineState = R_IDLE; // Ensure starting in IDLE
        routineActive = false;
        totalDescentPumpRunTimeThisRoutine = 0; // Reset timers on new start
        descentPumpActiveStartTime = 0;
        ascentNeutralizationTargetDuration = 0;
        stopSignalPending = false;

        String resp = "Started. Posting to " + laptopIpAddress + ":8000/depth. Initial depth (tare): " + String(initialDepth) + "m";
        server.send(200, "text/plain", resp);
        Serial.println(resp);
    } else {
        server.send(200, "text/plain", "Already started. IP updated to " + laptopIpAddress);
        Serial.println("Already started. IP updated to " + laptopIpAddress);
    }
}

void handleStopSignal() {
    Serial.println("Stop signal received by handler. Flag set for main task processing.");
    stopSignalPending = true; // Set the flag, TaskSensorAndSending will handle the logic
    server.send(200, "text/plain", "Stop signal acknowledged. Processing will occur in main task.");
}

void handleStartRoutine() {
    if (!hasStarted) {
        server.send(400, "text/plain", "Start float first (/start_signal)");
        return;
    }
    // Ensure the float is truly idle and no other routine/process is active
    if (routineActive || routineState != R_IDLE) {
        server.send(400, "text/plain", "Cannot start new routine. Float is not idle or another process is active. Current state: " + routineStateToString(routineState));
        return;
    }

    // If we reach here, it's safe to start
    routineActive = true;
    routineState = R_DESCENDING;
    routineStateStartTime = millis();
    packetsCollectedAtTarget = 0;
    previousTime = 0; 
    previousDepth = 0; 
    totalDescentPumpRunTimeThisRoutine = 0; 
    descentPumpActiveStartTime = 0;         
    ascentNeutralizationTargetDuration = 0; 
    routineJustCompletedLedActive = false;
    server.send(200, "text/plain", "Routine started: Descending to " + String(TARGET_DEPTH) + "m");
    Serial.println("Routine started: Descending to " + String(TARGET_DEPTH) + "m");
}


void handleRecalibrateDepth() {
    if (!hasStarted) {
        // Allow recalibration even if not fully "started" via start_signal,
        // as initialDepth is used once start_signal makes hasStarted true.
        // However, sensor must be initialized.
        Serial.println("Recalibrating depth zero point (float not formally started via /start_signal yet).");
    }

    sensor.read(); // Ensure fresh sensor reading
    float currentRawDepth = sensor.depth();

    if (isnan(currentRawDepth)) {
        String errorMsg = "Error: Failed to read valid depth from sensor for recalibration.";
        Serial.println(errorMsg);
        server.send(500, "text/plain", errorMsg);
        return;
    }

    initialDepth = currentRawDepth;
    previousDepth = 0; // Reset relative depth tracking
    // previousTime = 0; // Resetting previousTime might cause a large velocity spike on the next reading if hasStarted is true.
                       // It's safer to let velocity calculation continue with the existing previousTime.
                       // The depth reference change is the key part.

    String resp = "Depth recalibrated. New initial (tare) depth: " + String(initialDepth) + "m. Current relative depth is now ~0m.";
    Serial.println(resp);
    server.send(200, "text/plain", resp);
}

void handlePumpAscend() {
    if (routineActive && hasStarted) { server.send(400, "text/plain", "Pump control is automatic during routine."); return; }
    pumpAscend();
    server.send(200, "text/plain", "Manual: Pump ascending");
    Serial.println("Manual: Pump ascending");
}
void handlePumpDescend() {
    if (routineActive && hasStarted) { server.send(400, "text/plain", "Pump control is automatic during routine."); return; }
    pumpDescend();
    server.send(200, "text/plain", "Manual: Pump descending");
    Serial.println("Manual: Pump descending");
}
void handlePumpStop() {
    if (routineActive && hasStarted) { server.send(400, "text/plain", "Pump control is automatic during routine."); return; }
    pumpOff();
    server.send(200, "text/plain", "Manual: Pump stopped");
    Serial.println("Manual: Pump stopped");
}

// Task on core 0: WiFi & HTTP server
void TaskWifiServer(void *pvParameters) {
    unsigned long lastWifiCheckTime = 0;

    for (;;) {
        server.handleClient(); // Handle HTTP client requests

        unsigned long currentTime = millis();

        // Check and manage WiFi connection status periodically
        if (currentTime - lastWifiCheckTime >= 1000) { // Check status every 1 second
            lastWifiCheckTime = currentTime;

            if (WiFi.status() != WL_CONNECTED) {
                wifiFlag = false;
                // Attempt to reconnect if not connected and interval has passed
                if (currentTime - lastWifiReconnectAttempt >= WIFI_RECONNECT_INTERVAL) {
                    Serial.println("WiFi disconnected. Attempting to reconnect...");
                    WiFi.disconnect(); // Optional: ensure clean state before reconnect
                    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
                    lastWifiReconnectAttempt = currentTime;
                }
            } else { // WiFi is connected
                long rssi = WiFi.RSSI();
                wifiFlag = (rssi >= RSSI_THRESHOLD);
                if (!wifiFlag) {
                    Serial.printf("WiFi connected but signal weak (RSSI: %ld). Data sending might be unreliable.\n", rssi);
                }
                // Reset reconnect attempt time if connection is successful
                // to ensure the next attempt is after a full interval if it disconnects again.
                lastWifiReconnectAttempt = currentTime; 
            }
        }
        vTaskDelay(pdMS_TO_TICKS(10)); // Short delay for server responsiveness
    }
}

// Task on core 1: Sensor, routine, queue, send
void TaskSensorAndSending(void *) {
    unsigned long lastReadTime = 0;
    float currentDepth = 0.0; 
    float currentVelocity = 0.0;
    String pumpActionStatus = "Idle"; 

    for (;;) {
        unsigned long now = millis();

        // --- Stop Signal Processing ---
        if (stopSignalPending) {
                    stopSignalPending = false; // Consume the flag
                    Serial.println("TASK: Processing Stop Signal...");

                    if (hasStarted && routineActive && totalDescentPumpRunTimeThisRoutine > 0) {
                        Serial.println("TASK Stop Signal: Routine was active with ballast. Transitioning to Neutralization.");
                        if (totalDescentPumpRunTimeThisRoutine > DESCENT_TIMER_COMPENSATION_OFFSET_MS) {
                            ascentNeutralizationTargetDuration = totalDescentPumpRunTimeThisRoutine - DESCENT_TIMER_COMPENSATION_OFFSET_MS;
                        } else {
                            ascentNeutralizationTargetDuration = 0; // Avoid underflow, effectively no neutralization if descent was too short
                        }
                        Serial.printf("Compensated ascentNeutralizationTargetDuration: %lu ms (from %lu ms)\n", ascentNeutralizationTargetDuration, totalDescentPumpRunTimeThisRoutine);
                        routineState = R_NEUTRALIZING_BALLAST;
                        neutralizationStateStartTime = now;
                        routineActive = false; 
                        pumpActionStatus = "R:StopSignal-Neutralize";
            } else {
                // No neutralization needed, or float wasn't started, or routine wasn't active. Perform full immediate stop.
                Serial.println("TASK Stop Signal: Performing immediate full stop.");
                hasStarted = false; // This is the master flag for overall operation
                routineActive = false;
                pumpOff();
                measurementQueue.flush(); // Clear queue on full stop
                routineState = R_IDLE;
                packetsCollectedAtTarget = 0;
                routineJustCompletedLedActive = false;
                totalDescentPumpRunTimeThisRoutine = 0; 
                ascentNeutralizationTargetDuration = 0;
                descentPumpActiveStartTime = 0;
                pumpActionStatus = "M:StoppedBySignal";  
            }
        }

        sensor.read();
        float rawSensorDepth = sensor.depth();

        if (isnan(rawSensorDepth) || rawSensorDepth < -10 || rawSensorDepth > 1000) { 
            Serial.println("WARNING: Invalid raw sensor reading detected! Skipping this cycle's processing.");
            pumpActionStatus = "SensorErr";
        } else {
            if (hasStarted) { // Only process if the float is "started"
                currentDepth = rawSensorDepth - initialDepth;

                if (previousTime > 0) { 
                    float dt = (now - previousTime) / 1000.0;
                    if (dt > 0.001) { 
                        currentVelocity = (currentDepth - previousDepth) / dt;
                    } else {
                        currentVelocity = 0; 
                    }
                } else {
                     currentVelocity = 0; 
                }
                // previousDepth updated later

                // Default pump status, will be overwritten by state logic
                // pumpActionStatus = "Idle"; // This will be set by specific states

                // --- Main State Machine ---
                // routineActive controls the primary mission states (DESCENDING, COLLECTING, ASCENDING).
                // R_EMERGENCY_ASCENT and R_NEUTRALIZING_BALLAST are system states that can override/follow a routine.
                switch (routineState) {
                    case R_DESCENDING:
                        if (!routineActive) { // Should not happen if logic is correct, but as a safeguard
                            pumpOff(); routineState = R_IDLE; descentPumpActiveStartTime = 0; pumpActionStatus = "R:IdleAbortDesc"; break;
                        }
                        // Accumulate descent pump ON time
                        if (digitalRead(PUMP_DESC_PIN) == HIGH) { // Check if pump is actually ON
                            if (descentPumpActiveStartTime == 0) { // If it just turned ON
                                descentPumpActiveStartTime = now;
                            }
                            // Add time since last check if it was already on
                            totalDescentPumpRunTimeThisRoutine += (now - descentPumpActiveStartTime); 
                            descentPumpActiveStartTime = now; // Reset start time for next segment calculation
                        } else {
                            descentPumpActiveStartTime = 0; // Pump is OFF
                        }
                        
                        // SAFETY CHECK: Max descent pump duration
                        if (totalDescentPumpRunTimeThisRoutine >= MAX_TOTAL_DESCENT_PUMP_TIME) {
                            Serial.printf("EMERGENCY: Total descent pump run time %lu ms exceeded limit %lu ms. Initiating emergency ascent.\n", totalDescentPumpRunTimeThisRoutine, MAX_TOTAL_DESCENT_PUMP_TIME);
                            pumpAscend(); 
                            descentPumpActiveStartTime = 0; 
                            routineState = R_EMERGENCY_ASCENT;
                            routineStateStartTime = now; 
                            pumpActionStatus = "R:EmergencyAscent-Start";
                            break; 
                        }

                        pumpActionStatus = "R:Descend-VelCtrl";
                        if (currentDepth >= (TARGET_DEPTH - ROUTINE_TARGET_APPROACH_THRESHOLD)) {
                            pumpOff();
                            descentPumpActiveStartTime = 0; 
                            routineState = R_COLLECTING_DATA;
                            routineStateStartTime = now;
                            packetsCollectedAtTarget = 0; 
                            Serial.printf("ROUTINE: Approach target. State -> R_COLLECTING_DATA. Depth: %.2f\n", currentDepth);
                            pumpActionStatus = "R:ApproachTarget";
                        } else { 
                            if (currentVelocity > maxDescentVelocity && currentVelocity > 0.01) { 
                                pumpOff(); 
                                descentPumpActiveStartTime = 0; 
                                Serial.printf("ROUTINE: Descend too fast (%.2f m/s > %.2f). Pump OFF.\n", currentVelocity, maxDescentVelocity);
                                pumpActionStatus = "R:Descend-TooFast";
                            } else { 
                                pumpDescend(); 
                                // descentPumpActiveStartTime is handled at the top of R_DESCENDING
                                pumpActionStatus = "R:Descend-Normal";
                            }
                        }
                        break;

                    case R_COLLECTING_DATA:
                        if (!routineActive) { pumpOff(); routineState = R_IDLE; pumpActionStatus = "R:IdleAbortCollect"; break; }
                        descentPumpActiveStartTime = 0; // Ensure descent pump timer is not running
                        pumpActionStatus = "R:HoldDepth";
                        // ... (pump logic for holding depth) ...
                        if (currentDepth > TARGET_DEPTH + ROUTINE_DEPTH_TOLERANCE) {
                            pumpAscend(); pumpActionStatus = "R:HoldDepth-AdjustUp";
                        } else if (currentDepth < TARGET_DEPTH - ROUTINE_DEPTH_TOLERANCE) {
                            // Note: This descent is for adjustment. If it can be prolonged, it might need its own safety timer.
                            // For now, it does not contribute to totalDescentPumpRunTimeThisRoutine.
                            pumpDescend(); pumpActionStatus = "R:HoldDepth-AdjustDown";
                        } else {
                            pumpOff(); pumpActionStatus = "R:HoldDepth-Stable";
                        }

                        if (packetsCollectedAtTarget >= PACKETS_AT_TARGET_GOAL || (now - routineStateStartTime >= routineWaitTime)) {
                            // ... (serial prints) ...
                            pumpAscend(); 
                            routineState = R_ASCENDING;
                            routineStateStartTime = now;
                            previousTime = 0; previousDepth = 0; 
                            pumpActionStatus = "R:StartAscent";
                        }
                        break;

                    case R_ASCENDING:
                        if (!routineActive) { pumpOff(); routineState = R_IDLE; pumpActionStatus = "R:IdleAbortAscend"; break; }
                        descentPumpActiveStartTime = 0; 
                        pumpActionStatus = "R:Ascend-VelCtrl";
                        if (currentDepth <= 0.1) { 
                            pumpOff(); 
                            Serial.println("ROUTINE: Reached surface.");
                            routineJustCompletedLedActive = true; 
                            ledRoutineCompleteStart = now;

                            if (totalDescentPumpRunTimeThisRoutine > 0) {
                                Serial.println("Initiating ballast neutralization.");
                                if (totalDescentPumpRunTimeThisRoutine > DESCENT_TIMER_COMPENSATION_OFFSET_MS) {
                                    ascentNeutralizationTargetDuration = totalDescentPumpRunTimeThisRoutine - DESCENT_TIMER_COMPENSATION_OFFSET_MS;
                                } else {
                                    ascentNeutralizationTargetDuration = 0;
                                }
                                Serial.printf("Compensated ascentNeutralizationTargetDuration: %lu ms (from %lu ms)\n", ascentNeutralizationTargetDuration, totalDescentPumpRunTimeThisRoutine);
                                routineState = R_NEUTRALIZING_BALLAST;
                                neutralizationStateStartTime = now;
                                pumpActionStatus = "R:StartNeutralize";
                            } else {
                                Serial.println("ROUTINE: Complete (no neutralization needed).");
                                routineActive = false; 
                                routineState = R_IDLE;
                                totalDescentPumpRunTimeThisRoutine = 0; 
                                pumpActionStatus = "R:CompleteNoNeutralize";
                            }
                        } else {
                            // ... (velocity control for ascent) ...
                            if (currentVelocity < -maxAscentVelocity && currentVelocity < -0.01) { 
                                pumpOff(); pumpActionStatus = "R:Ascend-TooFast";
                            } else { 
                                pumpAscend(); pumpActionStatus = "R:Ascend-Normal";
                            }
                        }
                        break;
                    
                    case R_EMERGENCY_ASCENT:
                        descentPumpActiveStartTime = 0; 
                        pumpActionStatus = "R:EmergencyAscent-Active";
                        pumpAscend(); 

                        if (currentDepth <= 0.2) { 
                            pumpOff();
                            Serial.println("ROUTINE: Emergency ascent to safe depth complete.");

                            if (totalDescentPumpRunTimeThisRoutine > 0) {
                                Serial.println("Initiating ballast neutralization post-emergency.");
                                if (totalDescentPumpRunTimeThisRoutine > DESCENT_TIMER_COMPENSATION_OFFSET_MS) {
                                    ascentNeutralizationTargetDuration = totalDescentPumpRunTimeThisRoutine - DESCENT_TIMER_COMPENSATION_OFFSET_MS;
                                } else {
                                    ascentNeutralizationTargetDuration = 0;
                                }
                                Serial.printf("Compensated ascentNeutralizationTargetDuration: %lu ms (from %lu ms)\n", ascentNeutralizationTargetDuration, totalDescentPumpRunTimeThisRoutine);
                                routineState = R_NEUTRALIZING_BALLAST;
                                neutralizationStateStartTime = now;
                                pumpActionStatus = "R:EmergencyNeutralize";
                            } else {
                                Serial.println("ROUTINE: Emergency complete (no neutralization needed).");
                                routineActive = false; 
                                routineState = R_IDLE; 
                                totalDescentPumpRunTimeThisRoutine = 0; 
                                pumpActionStatus = "R:EmergencyCompleteNoNeutralize";
                            }
                        }
                        break;

                    case R_NEUTRALIZING_BALLAST:
                        pumpActionStatus = "R:Neutralizing";
                        descentPumpActiveStartTime = 0; // Not descending
                        if (ascentNeutralizationTargetDuration > 0 && (now - neutralizationStateStartTime < ascentNeutralizationTargetDuration)) {
                            pumpAscend();
                        } else {
                            pumpOff();
                            Serial.println("ROUTINE: Ballast neutralization complete.");
                            routineState = R_IDLE; 
                            routineActive = false; // Mark routine as fully ended now
                            totalDescentPumpRunTimeThisRoutine = 0; // Reset after use
                            ascentNeutralizationTargetDuration = 0;
                            pumpActionStatus = "R:NeutralizeComplete";
                            // If a stop signal triggered this, hasStarted is still true.
                            // The float is now idle and safe. A subsequent stop signal would do an immediate full stop.
                        }
                        break;

                    case R_IDLE: 
                        // If routineActive is true here, it's an anomaly or means it was just set false by another state.
                        if (routineActive) {
                             // This case might be hit if routineActive was just set to false by a completing state in the same loop cycle.
                             // Serial.println("Warning: In R_IDLE but routineActive is true. Forcing pump off.");
                             // routineActive = false; // Ensure it's false
                        }
                        pumpOff(); // Ensure pumps are off in idle
                        descentPumpActiveStartTime = 0;
                        // totalDescentPumpRunTimeThisRoutine should be 0 if truly idle.
                        if (digitalRead(PUMP_DESC_PIN) == HIGH || digitalRead(PUMP_ASC_PIN) == HIGH) { // Manual override check
                            // This part is tricky if manual commands are allowed while hasStarted=true but routineActive=false
                            // For now, assume R_IDLE means pumps should be off unless manually commanded by HTTP
                        }
                        if (pumpActionStatus != "R:NeutralizeComplete" && pumpActionStatus != "R:CompleteNoNeutralize" && pumpActionStatus != "R:EmergencyCompleteNoNeutralize") {
                           // Avoid overwriting final status messages from completed routines
                           if (digitalRead(PUMP_DESC_PIN) == HIGH) pumpActionStatus = "M:DescendActiveInIdle"; // Should not happen with current logic
                           else if (digitalRead(PUMP_ASC_PIN) == HIGH) pumpActionStatus = "M:AscendActiveInIdle"; // Should not happen
                           else pumpActionStatus = "M:Idle/Off";
                        }
                        break;
                    default:
                        Serial.println("ERROR: Unknown routine state!");
                        pumpOff();
                        routineActive = false;
                        routineState = R_IDLE;
                        pumpActionStatus = "R:ErrorUnknownState";
                        break;
                }

                // Update previousDepth *after* velocity calculation for the current cycle
                previousDepth = currentDepth; 

                if (now - lastReadTime >= currentReadInterval) {
                    lastReadTime = now; 
                    float pressureForData = sensor.pressure(); 
                    unsigned long elapsed = now - startTime;

                    Measurement m = {elapsed, currentDepth, pressureForData, COMPANY_NUMBER, currentVelocity, pumpActionStatus};
                    if (!measurementQueue.push(&m)) {
                        Serial.println("WARNING: Queue full - data point lost!");
                    } else {
                        Serial.printf("DATA: t=%lu, d=%.2f, v=%.2f, P=%s (Q:%d)\n",
                                      elapsed / 1000, currentDepth, currentVelocity, pumpActionStatus.c_str(), measurementQueue.getCount());
                        if (routineActive && routineState == R_COLLECTING_DATA) {
                            if (abs(currentDepth - TARGET_DEPTH) <= ROUTINE_DEPTH_TOLERANCE) {
                                packetsCollectedAtTarget++;
                                Serial.printf("  Packet %d/%d collected at target depth.\n", packetsCollectedAtTarget, PACKETS_AT_TARGET_GOAL);
                            }
                        }
                    }
                }
            } 
            else { // hasStarted is false (float is stopped or stopping)
                // Ensure all critical state variables are reset if float is stopped
                previousTime = 0;
                previousDepth = 0;
                currentVelocity = 0; 
                descentPumpActiveStartTime = 0; 
                totalDescentPumpRunTimeThisRoutine = 0;
                ascentNeutralizationTargetDuration = 0;
                routineActive = false;
                routineState = R_IDLE;
                packetsCollectedAtTarget = 0;
                if (digitalRead(PUMP_DESC_PIN) == HIGH || digitalRead(PUMP_ASC_PIN) == HIGH) {
                    pumpOff(); // Ensure pumps are off if stopped
                }
                pumpActionStatus = "M:Stopped";
            }
            // Update previousTime for the next cycle's dt calculation, regardless of 'hasStarted' for the main loop timing
            previousTime = now; 
        } 


        if (wifiFlag && !measurementQueue.isEmpty()) {
            if (hasStarted) { 
                static unsigned long lastSendAttempt = 0;
                unsigned long now_for_send = millis(); 

                if (now_for_send - lastSendAttempt >= SEND_INTERVAL) {
                    lastSendAttempt = now_for_send;
                    Measurement batch[SEND_BATCH_SIZE];
                    int count = 0;

                    while(count < SEND_BATCH_SIZE && measurementQueue.pop(&batch[count])) {
                        count++;
                    }

                    if (count > 0) {
                        if (hasStarted) { 
                            if (sendMeasurements(batch, count)) {
                                Serial.printf("Sent %d measurements (Queue: %d)\n", count, measurementQueue.getCount());
                                lastSuccessfulSend = now_for_send;
                                lastSendSuccessful = true;
                            } else {
                                if (hasStarted) {
                                    Serial.printf("Send failed for %d measurements, requeueing (Queue: %d)\n", count, measurementQueue.getCount());
                                    lastSendSuccessful = false;
                                    bool requeueFull = false;
                                    for (int i = count - 1; i >= 0; i--) { 
                                        if (!measurementQueue.push(&batch[i])) {
                                            Serial.printf("WARNING: Failed to requeue data point t=%lu. Queue full on requeue.\n", batch[i].timeSinceStart);
                                            requeueFull = true;
                                        }
                                    }
                                } else {
                                    Serial.printf("Send failed for %d. Float stopped during send. Discarding. (Queue: %d)\n", count, measurementQueue.getCount());
                                }
                            }
                        } else {
                            Serial.printf("Float stopped after pop. Discarding %d popped measurements. (Queue: %d)\n", count, measurementQueue.getCount());
                        }
                    }
                }
            } 
        }

        // LED Status Logic
        if (routineJustCompletedLedActive) {
            if (now - ledRoutineCompleteStart < LED_ROUTINE_COMPLETE_DURATION) {
                setStripColor(255, 255, 255); 
            } else {
                routineJustCompletedLedActive = false; 
            }
        }
        
        if (!routineJustCompletedLedActive) { 
            if (!hasStarted) {
                if (!wifiFlag) {
                    setStripColor(255, 0, 0); 
                } else { 
                    if (now - lastBlinkTime > (LED_BLINK_INTERVAL_NOT_STARTED / 2) ) {
                        lastBlinkTime = now;
                        blinkState = !blinkState;
                    }
                    if (blinkState) setStripColor(255, 0, 0); 
                    else setStripColor(0, 255, 0);    
                }
            } else { 
                if (!routineActive) { 
                    if (wifiFlag) setStripColor(0, 255, 0);   
                    else setStripColor(255, 0, 0);            
                } else { 
                    uint8_t base_r, base_g, base_b;
                    if (measurementQueue.getCount() > 20) { 
                        base_r = 255; base_g = 255; base_b = 0;
                    } else { 
                        base_r = 0; base_g = 0; base_b = 255;
                    }

                    if (now - lastBlinkTime > (LED_BLINK_INTERVAL_ROUTINE / 2) ) {
                        lastBlinkTime = now;
                        blinkState = !blinkState;
                    }

                    if (blinkState) { 
                        if (!wifiFlag) setStripColor(255, 0, 0); 
                        else setStripColor(0, 255, 0);           
                    } else { 
                        setStripColor(base_r, base_g, base_b);
                    }
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(50)); 
    }
}

void setup() {
    Serial.begin(115200);
    unsigned long setupStartTime = millis();
    while(!Serial && (millis() - setupStartTime < 3000)); 

    pinMode(NEOPIXEL_POWER_PIN, OUTPUT);
    digitalWrite(NEOPIXEL_POWER_PIN, HIGH); 
    strip.begin();
    strip.setBrightness(30); 
    setStripColor(255, 0, 0); 

    pinMode(PUMP_DESC_PIN, OUTPUT);
    pinMode(PUMP_ASC_PIN, OUTPUT);
    pumpOff();

    // Initial WiFi connection attempt in setup
    Serial.print("Connecting to WiFi");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    unsigned long wifiStartTime = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - wifiStartTime < 15000)) { // 15s timeout for initial attempt
        delay(250);
        Serial.print('.');
    }

    if(WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());
        wifiFlag = (WiFi.RSSI() >= RSSI_THRESHOLD);
        lastWifiReconnectAttempt = millis(); // Set initial time if connected
    } else {
        Serial.println("\nInitial WiFi connection failed! Will attempt reconnection periodically.");
        wifiFlag = false;
        // lastWifiReconnectAttempt will be 0, so first reconnect attempt in task will happen soon.
    }
    
    server.on("/start_signal", HTTP_GET, handleStartSignal);
    server.on("/stop_signal", HTTP_GET, handleStopSignal);
    server.on("/start_routine", HTTP_GET, handleStartRoutine);
    server.on("/set_target_depth", HTTP_GET, handleSetTargetDepth);
    server.on("/set_wait_time", HTTP_GET, handleSetWaitTime);
    server.on("/pump_ascend", HTTP_GET, handlePumpAscend);
    server.on("/pump_descend", HTTP_GET, handlePumpDescend);
    server.on("/pump_stop", HTTP_GET, handlePumpStop);
    server.on("/status", HTTP_GET, handleStatus);
    server.on("/set_company_number", HTTP_GET, handleSetCompanyNumber);
    server.on("/recalibrate_depth", HTTP_GET, handleRecalibrateDepth); // Added new handler

    server.begin();
    Serial.println("HTTP server started");

    Wire.begin();
    sensor.setModel(MS5837::MS5837_02BA); 
    if (!sensor.init()) {
        Serial.println("CRITICAL: Sensor init failed! Check wiring and I2C. Restarting in 5s.");
        setStripColor(255,0,0); delay(50); setStripColor(0,0,0); delay(50); setStripColor(255,0,0); 
        delay(5000);
        ESP.restart();
    } else {
        Serial.println("MS5837 Sensor initialized.");
    }
    sensor.setFluidDensity(1029); 

    xTaskCreatePinnedToCore(TaskWifiServer, "TaskWifiServer", 3584, NULL, 1, NULL, 0); // Increased stack for WiFi task
    xTaskCreatePinnedToCore(TaskSensorAndSending, "TaskSensorAndSending", 6144, NULL, 2, NULL, 1); 
    
    Serial.println("Setup complete. Tasks running.");
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(1000)); 
}

// LED State Table:
// Condition                               | LED Color/Pattern
// ----------------------------------------|----------------------------------------------------
// Not Started, WiFi Not Connected         | Solid RED
// Not Started, WiFi Connected             | Blinking (0.5s RED / 0.5s GREEN)
// Started, WiFi Connected, Routine Idle   | Solid GREEN
// Started, WiFi Not Connected, Routine Idle| Solid RED (Indicates WiFi loss after start)
// Routine Active:                          |
//   Base Color:                           |
//     Queue <= 20 measurements            | BLUE
//     Queue > 20 measurements             | YELLOW
//   Overlay Blink (every 2s period):       |
//     WiFi Not Connected                  | Alternates Base Color (1s) / RED (1s)
//     WiFi Connected                      | Alternates Base Color (1s) / GREEN (1s)
// Routine Complete                        | Solid WHITE for 5 seconds, then reverts to 'Started' state LED.