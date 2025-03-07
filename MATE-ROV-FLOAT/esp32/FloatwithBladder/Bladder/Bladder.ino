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
};

// Use cppQueue: record size = sizeof(Measurement), capacity = 400, FIFO, no overwrite
cppQueue measurementQueue(sizeof(Measurement), 400, FIFO, false);

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

// -------------------- /start_signal handler --------------------
void handleStartSignal() {
  if (server.hasArg("ip_address")) {
    laptopIpAddress = server.arg("ip_address");
    if (!hasStarted) {
      hasStarted = true;
      startTime = millis();
      sensor.read();
      initialDepth = sensor.depth();  // baseline depth
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
  measurementQueue.flush();
  setStripColor(255, 0, 0); // LED RED

  // Reset timing variables
  startTime = millis();
  initialDepth = 0.0;

  // Also restore the normal data capture rate and stop pump
  currentReadInterval = NORMAL_READ_INTERVAL;
  routineState = R_IDLE;
  pumpOff();
  
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

// -------------------- /start_routine handler --------------------
void handleStartRoutine() {
  if (!hasStarted) {
    server.send(400, "text/plain", "Float not started yet. Please start the float first.");
    return;
  }
  if (!routineActive) {
    routineActive = true;
    routineState = R_DESCENDING;
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

  for (;;) {
    currentMillis = millis();

    // 1) If not started, keep LED RED and wait
    if (!hasStarted) {
      setStripColor(255, 0, 0); // RED
      vTaskDelay(500 / portTICK_PERIOD_MS);
      continue;
    }

    // Read sensor data once per loop iteration for both routine and normal reading
    sensor.read();
    float currentDepth = sensor.depth() - initialDepth;

    // -------------------- Routine State Machine --------------------
    if (routineActive) {
      switch (routineState) {
        case R_DESCENDING:
          // Activate pump to descend
          pumpDescend();
          if (currentDepth >= 2.5) {
            pumpOff();
            routineState = R_WAITING;
            routineWaitStart = currentMillis;
            Serial.println("Routine: Target depth reached. Holding position...");
          }
          break;

        case R_WAITING:
          // Hold for at least 42 seconds
          if (currentMillis - routineWaitStart >= 42000) {  // 42 seconds
            pumpAscend();
            routineState = R_ASCENDING;
            Serial.println("Routine: Hold complete. Ascending initiated...");
          }
          break;

        case R_ASCENDING:
          // Wait until float has ascended near the surface (e.g., depth ≤ 0.5 m)
          if (currentDepth <= 0.5) {
            pumpOff();
            routineState = R_IDLE;
            routineActive = false;
            Serial.println("Routine: Ascended. Routine complete.");
          }
          break;

        case R_IDLE:
        default:
          break;
      }
    }

    // 2) Normal sensor reading & data queuing (uses currentReadInterval)
    if ((currentMillis - lastReadTime) >= currentReadInterval) {
      lastReadTime = currentMillis;

      float pressure = sensor.pressure();
      unsigned long elapsed = currentMillis - startTime;

      Measurement m;
      m.timeSinceStart = elapsed;
      m.depth          = currentDepth;
      m.pressure       = pressure;
      m.companyNum     = COMPANY_NUMBER;

      if (!measurementQueue.push(&m)) {
        Serial.println("Queue is full, could not push new measurement!");
      } else {
        Serial.printf("Enqueued: time=%lu ms, depth=%.3f, pressure=%.3f\n",
                      elapsed, currentDepth, pressure);
      }
    }

    // 3) If WiFi is good and queue has data, send a batch
    if (wifiFlag && !measurementQueue.isEmpty()) {
      for (int i = 0; i < SEND_BATCH_SIZE; i++) {
        if (measurementQueue.isEmpty()) break;

        Measurement frontItem;
        if (!measurementQueue.peek(&frontItem)) break;

        float timeSec = frontItem.timeSinceStart / 1000.0f;
        StaticJsonDocument<256> doc;
        doc["time"]     = timeSec;
        doc["depth"]    = frontItem.depth;
        doc["pressure"] = frontItem.pressure;
        doc["company"]  = frontItem.companyNum;

        String payload;
        serializeJson(doc, payload);

        if (laptopIpAddress.isEmpty()) {
          Serial.println("No laptop IP, can't send. Breaking out...");
          break;
        }

        String postUrl = "http://" + laptopIpAddress + ":8000/depth";
        http.begin(postUrl);
        http.addHeader("Content-Type", "application/json");
        int code = http.POST(payload);

        if (code == 200) {
          String resp = http.getString();
          if (resp.indexOf("DATARECEIVED") >= 0 || resp.indexOf("OK") >= 0) {
            measurementQueue.drop();
            Serial.println("Packet sent OK. (Popped from queue)");
            setStripColor(0, 0, 255); // LED BLUE
            vTaskDelay(1000 / portTICK_PERIOD_MS);
          }
          else {
            Serial.println("Server response not recognized. Stopping batch.");
            http.end();
            break;
          }
        }
        else {
          Serial.printf("HTTP POST failed, code = %d\n", code);
          http.end();
          break;
        }
        http.end();
      }
      vTaskDelay(1000 / portTICK_PERIOD_MS);
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
