#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <cppQueue.h>
#include <Wire.h>
#include <MS5837.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>

// -------------------- CONFIGURATION --------------------
#define WIFI_SSID "NR-3"
#define WIFI_PASSWORD "Radhi02@Nagi22"
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
unsigned long currentSendInterval = SEND_INTERVAL; // Will be fixed to SEND_INTERVAL
unsigned long lastSuccessfulSend = 0;
bool lastSendSuccessful = false; // Retained for potential future adaptive logic, but not used currently

// Batch send size
#define SEND_BATCH_SIZE 1 // Send one packet at a time

// Pump control pins
#define PUMP_DESC_PIN 27 // fill ballast
#define PUMP_ASC_PIN 12  // empty ballast

// Routine control
float TARGET_DEPTH = 2.5;      // Target depth for routine, e.g., 2.5m
const float ROUTINE_DEPTH_TOLERANCE = 0.5; // ±0.5m for data collection at target
const float ROUTINE_TARGET_APPROACH_THRESHOLD = 0.5; // Start fine control 0.5m before target
unsigned long routineWaitTime = 80000; // Max time to spend in data collection state (45 seconds)

// Routine state
enum RoutineState { R_IDLE, R_DESCENDING, R_COLLECTING_DATA, R_ASCENDING };
volatile bool routineActive = false;
volatile RoutineState routineState = R_IDLE;
unsigned long routineStateStartTime = 0; // Time when current routine state started
int packetsCollectedAtTarget = 0;
const int PACKETS_AT_TARGET_GOAL = 10;

// Velocity limits
float maxDescentVelocity = 0.1; // m/s
float maxAscentVelocity = 0.1;  // m/s (positive value for magnitude)

unsigned long previousTime = 0;
float previousDepth = 0.0;

volatile bool wifiFlag = false;
volatile bool hasStarted = false;
unsigned long currentReadInterval = NORMAL_READ_INTERVAL; // Fixed to NORMAL_READ_INTERVAL

// Measurement queue
struct Measurement {
    unsigned long timeSinceStart;
    float depth;
    float pressure;
    int companyNum;
    float velocity;
    String pumpStatus;
    // PID fields removed
};

cppQueue measurementQueue(sizeof(Measurement), 800, FIFO, false);

WebServer server(80);
HTTPClient http;
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
#define LED_BLINK_INTERVAL_NOT_STARTED 1000 // 1s period for not started blink
#define LED_BLINK_INTERVAL_ROUTINE 2000     // 2s period for routine blink
#define LED_ROUTINE_COMPLETE_DURATION 5000  // 5s for white LED

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
    if (!wifiFlag || laptopIpAddress.isEmpty() || count <= 0)
        return false;

    DynamicJsonDocument doc(1024 + count * 256); // Adjusted size
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

    // Ensure HTTPClient is re-initialized for each request if it's a global object
    // or manage its lifecycle carefully. For simplicity, begin/end each time.
    HTTPClient localHttp; // Use a local instance to avoid state issues with global http
    localHttp.begin("http://" + laptopIpAddress + ":8000/depth");
    localHttp.addHeader("Content-Type", "application/json");
    int code = localHttp.POST(payload);
    localHttp.end();
    return (code == 200);
}

// Helper function to convert routine state to string
String routineStateToString(RoutineState state) {
    switch (state) {
    case R_IDLE: return "idle";
    case R_DESCENDING: return "descending";
    case R_COLLECTING_DATA: return "collecting_data_at_target";
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

void handleStatus() {
    DynamicJsonDocument doc(1024);

    doc["started"] = hasStarted;
    doc["uptime_seconds"] = millis() / 1000;
    doc["free_heap"] = ESP.getFreeHeap();
    doc["company_number"] = COMPANY_NUMBER;

    JsonObject wifi = doc.createNestedObject("wifi");
    wifi["rssi"] = WiFi.RSSI();
    wifi["connected"] = (WiFi.status() == WL_CONNECTED);
    wifi["good_signal"] = wifiFlag;
    wifi["ip"] = WiFi.localIP().toString();

    JsonObject queue = doc.createNestedObject("queue");
    queue["current_size"] = measurementQueue.getCount();
    queue["capacity"] = 800; // Max capacity of cppQueue
    queue["percent_full"] = (measurementQueue.getCount() * 100) / 800;
    queue["read_interval_ms"] = currentReadInterval;
    queue["send_interval_ms"] = SEND_INTERVAL;


    JsonObject depth_info = doc.createNestedObject("depth");
    float currentDepth = NAN;
    if(hasStarted) currentDepth = sensor.depth() - initialDepth; else currentDepth = sensor.depth(); // Show raw if not started
    depth_info["current"] = currentDepth;
    depth_info["target"] = TARGET_DEPTH;
    depth_info["target_tolerance"] = ROUTINE_DEPTH_TOLERANCE;
    depth_info["pressure"] = sensor.pressure();
    
    JsonObject velocity_info = doc.createNestedObject("velocity");
    float tempCurrentVelocity = 0;
    if (previousTime > 0 && hasStarted) {
        unsigned long dt_ms = millis() - previousTime;
        if (dt_ms > 0) {
            float dt_s = dt_ms / 1000.0;
            // Use the same currentDepth as calculated above for consistency
            tempCurrentVelocity = (currentDepth - previousDepth) / dt_s;
        }
    }
    velocity_info["current"] = tempCurrentVelocity;
    velocity_info["max_descent_config"] = maxDescentVelocity;
    velocity_info["max_ascent_config"] = maxAscentVelocity;

    JsonObject routine = doc.createNestedObject("routine");
    routine["active"] = routineActive;
    routine["state"] = routineStateToString(routineState);
    routine["wait_time_seconds_config"] = routineWaitTime / 1000;
    routine["packets_collected_at_target"] = packetsCollectedAtTarget;
    routine["packets_goal_at_target"] = PACKETS_AT_TARGET_GOAL;

    if (routineActive && routineState == R_COLLECTING_DATA) {
        unsigned long elapsedWait = millis() - routineStateStartTime;
        routine["time_in_collection_state_seconds"] = elapsedWait / 1000;
        routine["collection_timeout_remaining_seconds"] = (routineWaitTime > elapsedWait) ? (routineWaitTime - elapsedWait) / 1000 : 0;
    }

    JsonObject pump = doc.createNestedObject("pump");
    bool pumpDescActive = digitalRead(PUMP_DESC_PIN) == HIGH;
    bool pumpAscActive = digitalRead(PUMP_ASC_PIN) == HIGH;
    if (pumpDescActive) pump["state"] = "descending";
    else if (pumpAscActive) pump["state"] = "ascending";
    else pump["state"] = "off";

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
    if (d < 0 || d > 10) { // Allow 0m as a target
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
        sensor.read(); // Ensure sensor has a fresh reading before taking initial depth
        initialDepth = sensor.depth();
        previousTime = 0;      // Reset for velocity calculation
        previousDepth = 0;     // Reset for velocity calculation
        measurementQueue.flush(); // Clear any old data
        String resp = "Started. Posting to " + laptopIpAddress + ":8000/depth. Initial depth (tare): " + String(initialDepth) + "m";
        server.send(200, "text/plain", resp);
        Serial.println(resp);
    } else {
        server.send(200, "text/plain", "Already started. IP updated to " + laptopIpAddress);
    }
}

void handleStopSignal() {
    hasStarted = false;
    routineActive = false;
    pumpOff();
    measurementQueue.flush();
    routineState = R_IDLE;
    packetsCollectedAtTarget = 0;
    routineJustCompletedLedActive = false; // Reset LED flag
    server.send(200, "text/plain", "Float stopped and reset");
    Serial.println("Float stopped and reset.");
}

void handleStartRoutine() {
    if (!hasStarted) {
        server.send(400, "text/plain", "Start float first (/start_signal)");
        return;
    }
    if (!routineActive) {
        routineActive = true;
        routineState = R_DESCENDING;
        routineStateStartTime = millis();
        packetsCollectedAtTarget = 0;
        previousTime = 0; // Reset for velocity calc at start of routine segments
        previousDepth = 0;
        routineJustCompletedLedActive = false;
        pumpDescend(); // Start by descending
        server.send(200, "text/plain", "Routine started: Descending to " + String(TARGET_DEPTH) + "m");
        Serial.println("Routine started: Descending to " + String(TARGET_DEPTH) + "m");
    } else {
        server.send(200, "text/plain", "Routine already active in state: " + routineStateToString(routineState));
    }
}

void handlePumpAscend() {
    if (routineActive) { server.send(400, "text/plain", "Pump control is automatic during routine."); return; }
    pumpAscend();
    server.send(200, "text/plain", "Manual: Pump ascending");
    Serial.println("Manual: Pump ascending");
}
void handlePumpDescend() {
    if (routineActive) { server.send(400, "text/plain", "Pump control is automatic during routine."); return; }
    pumpDescend();
    server.send(200, "text/plain", "Manual: Pump descending");
    Serial.println("Manual: Pump descending");
}
void handlePumpStop() {
    if (routineActive) { server.send(400, "text/plain", "Pump control is automatic during routine."); return; }
    pumpOff();
    server.send(200, "text/plain", "Manual: Pump stopped");
    Serial.println("Manual: Pump stopped");
}

// Task on core 0: WiFi & HTTP server
void TaskWifiServer(void *) {
    for (;;) {
        server.handleClient();
        wifiFlag = (WiFi.status() == WL_CONNECTED && WiFi.RSSI() >= RSSI_THRESHOLD);
        vTaskDelay(10 / portTICK_PERIOD_MS);
    }
}

// Task on core 1: Sensor, routine, queue, send
void TaskSensorAndSending(void *) {
    unsigned long lastReadTime = 0;
    float currentDepth = 0.0;
    float currentVelocity = 0.0;
    String pumpActionStatus = "Idle"; // Describes pump action taken in this cycle

    for (;;) {
        unsigned long now = millis();

        sensor.read();
        float rawSensorDepth = sensor.depth();

        if (isnan(rawSensorDepth) || rawSensorDepth < -10 || rawSensorDepth > 100) { // Basic validation
            Serial.println("WARNING: Invalid sensor reading detected! Skipping this cycle.");
            pumpActionStatus = "SensorErr";
        } else {
            if (hasStarted) {
                currentDepth = rawSensorDepth - initialDepth;
            } else {
                currentDepth = rawSensorDepth; // Show raw depth if not started
            }

            if (hasStarted && previousTime > 0) {
                float dt = (now - previousTime) / 1000.0;
                if (dt > 0.001) { // Avoid division by zero or tiny dt
                    currentVelocity = (currentDepth - previousDepth) / dt;
                } else {
                    currentVelocity = 0; // Or retain previous velocity if dt is too small
                }
            } else {
                 currentVelocity = 0; // No velocity if not started or first reading
            }
            // Update for next iteration AFTER using current values
            // previousDepth is updated after its use in velocity calculation for the current frame
            // previousTime is updated at the end of processing for this frame

            if (hasStarted) {
                pumpActionStatus = "Idle"; // Default if no specific action taken by routine
                if (routineActive) {
                    switch (routineState) {
                    case R_DESCENDING:
                        pumpActionStatus = "Descend-VelCtrl";
                        // Target is to reach ROUTINE_TARGET_APPROACH_THRESHOLD above TARGET_DEPTH
                        if (currentDepth >= (TARGET_DEPTH - ROUTINE_TARGET_APPROACH_THRESHOLD)) {
                            pumpOff();
                            routineState = R_COLLECTING_DATA;
                            routineStateStartTime = now;
                            packetsCollectedAtTarget = 0; // Reset for this phase
                            Serial.printf("ROUTINE: Reached approach for target. Switching to Data Collection. Depth: %.2f\n", currentDepth);
                            pumpActionStatus = "ApproachTarget";
                        } else {
                            // Velocity control for descent
                            if (currentVelocity > maxDescentVelocity && currentVelocity > 0.02) { // Descending too fast (added small positive check)
                                pumpOff(); // Or brief ascend
                                Serial.printf("ROUTINE: Descending too fast (%.2f m/s). Pump OFF.\n", currentVelocity);
                                pumpActionStatus = "Descend-TooFast";
                            } else {
                                pumpDescend(); // Continue descending
                            }
                        }
                        break;

                    case R_COLLECTING_DATA:
                        pumpActionStatus = "HoldDepth-Target";
                        // Maintain depth within TARGET_DEPTH ± ROUTINE_DEPTH_TOLERANCE
                        if (currentDepth > TARGET_DEPTH + ROUTINE_DEPTH_TOLERANCE) {
                            pumpAscend();
                            pumpActionStatus = "HoldDepth-AdjustUp";
                        } else if (currentDepth < TARGET_DEPTH - ROUTINE_DEPTH_TOLERANCE) {
                            pumpDescend();
                            pumpActionStatus = "HoldDepth-AdjustDown";
                        } else {
                            pumpOff(); // Within tolerance
                            pumpActionStatus = "HoldDepth-Stable";
                        }

                        // Check for transition conditions
                        if (packetsCollectedAtTarget >= PACKETS_AT_TARGET_GOAL || (now - routineStateStartTime >= routineWaitTime)) {
                            if (packetsCollectedAtTarget < PACKETS_AT_TARGET_GOAL) {
                                Serial.printf("ROUTINE: Data collection time (%.1fs) expired with %d/%d packets. Ascending.\n", routineWaitTime/1000.0, packetsCollectedAtTarget, PACKETS_AT_TARGET_GOAL);
                            } else {
                                Serial.printf("ROUTINE: Collected %d/%d packets at target. Ascending.\n", packetsCollectedAtTarget, PACKETS_AT_TARGET_GOAL);
                            }
                            pumpAscend(); // Start ascending
                            routineState = R_ASCENDING;
                            routineStateStartTime = now;
                            pumpActionStatus = "StartAscent";
                        }
                        break;

                    case R_ASCENDING:
                        pumpActionStatus = "Ascend-VelCtrl";
                        if (currentDepth <= 0.05) { // Reached surface (e.g., 0.5m)
                            pumpOff();
                            routineActive = false;
                            routineState = R_IDLE;
                            routineJustCompletedLedActive = true; // Trigger WHITE LED
                            ledRoutineCompleteStart = now;
                            Serial.println("ROUTINE: Complete. Reached surface.");
                            pumpActionStatus = "RoutineComplete";
                        } else {
                            // Velocity control for ascent (velocity is negative)
                            if (currentVelocity < -maxAscentVelocity && currentVelocity < -0.02) { // Ascending too fast (added small negative check)
                                pumpOff(); // Or brief descend
                                Serial.printf("ROUTINE: Ascending too fast (%.2f m/s). Pump OFF.\n", currentVelocity);
                                pumpActionStatus = "Ascend-TooFast";
                            } else {
                                pumpAscend(); // Continue ascending
                            }
                        }
                        break;
                    
                    case R_IDLE: // Should not be in R_IDLE if routineActive is true, but as a fallback
                        pumpOff();
                        pumpActionStatus = "RoutineIdleError";
                        break;
                    }
                } else { // Routine NOT active, but float IS started (manual mode or idle)
                    if (digitalRead(PUMP_DESC_PIN) == HIGH) pumpActionStatus = "Manual-Descend";
                    else if (digitalRead(PUMP_ASC_PIN) == HIGH) pumpActionStatus = "Manual-Ascend";
                    else pumpActionStatus = "Manual-Off";
                }

                // Data capture
                if (now - lastReadTime >= currentReadInterval) {
                    lastReadTime = now;
                    float pressure = sensor.pressure();
                    unsigned long elapsed = now - startTime;

                    Measurement m = {elapsed, currentDepth, pressure, COMPANY_NUMBER, currentVelocity, pumpActionStatus};
                    if (!measurementQueue.push(&m)) {
                        Serial.println("Queue full - data point lost!");
                    } else {
                        Serial.printf("DATA: t=%lu, d=%.2f, v=%.2f, P=%s (Q:%d)\n",
                                      elapsed / 1000, currentDepth, currentVelocity, pumpActionStatus.c_str(), measurementQueue.getCount());
                        // If in data collection phase and within tolerance, count packet
                        if (routineActive && routineState == R_COLLECTING_DATA) {
                            if (abs(currentDepth - TARGET_DEPTH) <= ROUTINE_DEPTH_TOLERANCE) {
                                packetsCollectedAtTarget++;
                                Serial.printf("  Packet %d/%d collected at target depth.\n", packetsCollectedAtTarget, PACKETS_AT_TARGET_GOAL);
                            }
                        }
                    }
                }
            } // end if(hasStarted)
            
            // Update previous values for next iteration's velocity calculation
            if(hasStarted) {
                previousDepth = currentDepth; // currentDepth for this frame becomes previousDepth for next
            }
            previousTime = now; // Time of this frame's readings/calculations

        } // end else (valid sensor reading)


        // Send data from queue
        if (wifiFlag && !measurementQueue.isEmpty()) {
            static unsigned long lastSendAttempt = 0;
            if (now - lastSendAttempt >= SEND_INTERVAL) {
                lastSendAttempt = now;
                Measurement batch[SEND_BATCH_SIZE]; // SEND_BATCH_SIZE is 1
                int count = 0;
                // Dequeue up to SEND_BATCH_SIZE items
                while(count < SEND_BATCH_SIZE && measurementQueue.pop(&batch[count])) {
                    count++;
                }

                if (count > 0) {
                    if (sendMeasurements(batch, count)) {
                        // Successful send, LED will be handled by main logic
                        Serial.printf("Sent %d measurements (Queue: %d)\n", count, measurementQueue.getCount());
                        lastSuccessfulSend = now; // For potential future use
                        lastSendSuccessful = true;
                    } else {
                        Serial.printf("Send failed for %d measurements, requeueing (Queue: %d)\n", count, measurementQueue.getCount());
                        lastSendSuccessful = false;
                        // Requeue in reverse order to maintain sequence (important if batch > 1)
                        bool requeueFull = false;
                        for (int i = count - 1; i >= 0; i--) {
                            if (!measurementQueue.push(&batch[i])) { // Push to front if possible, or just push
                                Serial.printf("WARNING: Failed to requeue data point t=%lu. Queue full on requeue.\n", batch[i].timeSinceStart);
                                requeueFull = true;
                            }
                        }
                        if(requeueFull) { /* Potentially flash RED for data loss on requeue */ }
                    }
                }
            }
        }

        // LED Status Logic
        if (routineJustCompletedLedActive) {
            if (now - ledRoutineCompleteStart < LED_ROUTINE_COMPLETE_DURATION) {
                setStripColor(255, 255, 255); // WHITE
            } else {
                routineJustCompletedLedActive = false; // Reset flag
            }
        }
        
        if (!routineJustCompletedLedActive) { // Only apply other LED logic if not in "routine complete white" phase
            if (!hasStarted) {
                if (!wifiFlag) {
                    setStripColor(255, 0, 0); // Solid RED
                } else { // WiFi connected, not started
                    if (now - lastBlinkTime > (LED_BLINK_INTERVAL_NOT_STARTED / 2) ) {
                        lastBlinkTime = now;
                        blinkState = !blinkState;
                    }
                    if (blinkState) setStripColor(255, 0, 0); // RED part of blink
                    else setStripColor(0, 255, 0);    // GREEN part of blink
                }
            } else { // Has started
                if (!routineActive) { // Started, routine idle
                    if (wifiFlag) setStripColor(0, 255, 0);   // Solid GREEN
                    else setStripColor(255, 0, 0);            // Solid RED (WiFi lost after start)
                } else { // Routine is active
                    uint8_t base_r, base_g, base_b;
                    if (measurementQueue.getCount() > 20) { // YELLOW base
                        base_r = 255; base_g = 255; base_b = 0;
                    } else { // BLUE base
                        base_r = 0; base_g = 0; base_b = 255;
                    }

                    if (now - lastBlinkTime > (LED_BLINK_INTERVAL_ROUTINE / 2) ) {
                        lastBlinkTime = now;
                        blinkState = !blinkState;
                    }

                    if (blinkState) { // Show WiFi status color
                        if (!wifiFlag) setStripColor(255, 0, 0); // Blink RED
                        else setStripColor(0, 255, 0);           // Blink GREEN
                    } else { // Show base color
                        setStripColor(base_r, base_g, base_b);
                    }
                }
            }
        }
        vTaskDelay(50 / portTICK_PERIOD_MS); // Loop roughly every 50ms
    }
}

void setup() {
    Serial.begin(115200);
    while(!Serial && millis() < 2000); // Wait for serial, but not forever

    pinMode(NEOPIXEL_POWER_PIN, OUTPUT);
    digitalWrite(NEOPIXEL_POWER_PIN, HIGH); // Power on NeoPixel
    strip.begin();
    strip.setBrightness(50); // Adjust brightness as needed (0-255)
    setStripColor(255, 0, 0); // Initial RED

    pinMode(PUMP_DESC_PIN, OUTPUT);
    pinMode(PUMP_ASC_PIN, OUTPUT);
    pumpOff();

    unsigned long wifiStartTime = millis();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print('.');
        if (millis() - wifiStartTime > 20000) { // 20 second timeout
            Serial.println("\nWiFi connection failed! Check credentials/signal. Will proceed without WiFi sending initially.");
            // ESP.restart(); // Or allow to continue without WiFi
            break; 
        }
    }
    if(WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());
    } else {
        Serial.println("\nContinuing without WiFi connection.");
    }
    

    // HTTP routes
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
    // Removed handlers: /set_pid, /toggle_pid_control, /set_pid_deadband,
    // /start_velocity, /stop_velocity, /set_velocity,
    // /set_depth_tolerance, /set_read_intervals

    server.begin();
    Serial.println("HTTP server started");

    Wire.begin();
    sensor.setModel(MS5837::MS5837_02BA); // Or your specific model
    if (!sensor.init()) {
        Serial.println("Sensor init failed! Check wiring and I2C.");
        // Potentially halt or indicate critical error
    } else {
        Serial.println("MS5837 Sensor initialized.");
    }
    sensor.setFluidDensity(1029); // kg/m^3 for saltwater

    wifiFlag = (WiFi.status() == WL_CONNECTED && WiFi.RSSI() >= RSSI_THRESHOLD); // Initial check

    xTaskCreatePinnedToCore(TaskWifiServer, "TaskWifiServer", 4096, NULL, 1, NULL, 0);
    xTaskCreatePinnedToCore(TaskSensorAndSending, "TaskSensorAndSending", 8192, NULL, 1, NULL, 1);
    
    Serial.println("Setup complete. Tasks running.");
}

void loop() {
    // Empty: all work is done in FreeRTOS tasks
    vTaskDelay(1000 / portTICK_PERIOD_MS); // Keep loop from starving watchdog if tasks somehow exit
}

// LED State Table:
// Condition                               | LED Color/Pattern
// ----------------------------------------|----------------------------------------------------
// Not Started, WiFi Not Connected         | Solid RED
// Not Started, WiFi Connected             | Blinking RED (1s period, 0.5s RED / 0.5s GREEN)
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