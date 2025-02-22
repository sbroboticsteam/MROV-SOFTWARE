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

// How often to read sensor (milliseconds)
#define READ_INTERVAL       2000

// How many items to attempt to send at once
#define SEND_BATCH_SIZE     5

// Shared flags
volatile bool wifiFlag   = false;  // True if WiFi connected & RSSI good
volatile bool hasStarted = false;  // True after /start_signal is called

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

// -------------------- TASK on CORE 0: WiFi & WebServer --------------------
void TaskWifiServer(void * pvParameters) {
  (void) pvParameters;  // unused

  for (;;) {
    // Handle any incoming HTTP requests
    server.handleClient();

    // Check WiFi connection + RSSI
    if (WiFi.status() == WL_CONNECTED) {
      long rssi = WiFi.RSSI(); // e.g. -60 dBm
      if (rssi >= RSSI_THRESHOLD) {
        wifiFlag = true;
      } else {
        wifiFlag = false;
        // Serial.printf("Connected but RSSI (%ld dBm) < %d dBm\n", rssi, RSSI_THRESHOLD);
      }
    } else {
      wifiFlag = false;
    }

    // Don't hog the CPU
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }
}

// -------------------- TASK on CORE 1: Sensor Reading & Queue Send --------------------
void TaskSensorAndSending(void * pvParameters) {
  (void) pvParameters;

  unsigned long lastReadTime   = 0;
  unsigned long currentMillis  = 0;

  for (;;) {
    currentMillis = millis();

    // 1) If we haven't started, keep LED RED and do nothing else
    if (!hasStarted) {
      setStripColor(255, 0, 0); // RED
      vTaskDelay(500 / portTICK_PERIOD_MS);
      continue;
    }

    // 2) If it's time to read sensor, do so and enqueue data
    if ((currentMillis - lastReadTime) >= READ_INTERVAL) {
      lastReadTime = currentMillis;

      sensor.read();
      float depth    = sensor.depth() - initialDepth;
      float pressure = sensor.pressure();
      unsigned long elapsed = currentMillis - startTime; // ms

      Measurement m;
      m.timeSinceStart = elapsed;
      m.depth          = depth;
      m.pressure       = pressure;
      m.companyNum     = COMPANY_NUMBER;

      bool pushed = measurementQueue.push(&m); // push to queue
      if (!pushed) {
        Serial.println("Queue is full, could not push new measurement!");
      } else {
        Serial.printf("Enqueued: time=%lu ms, depth=%.3f, pressure=%.3f\n",
                      elapsed, depth, pressure);
      }
    }

    // 3) If wifiFlag is true and the queue has data, try to send up to 5
    if (wifiFlag && !measurementQueue.isEmpty()) {
      // We'll do a batch of up to SEND_BATCH_SIZE
      for (int i = 0; i < SEND_BATCH_SIZE; i++) {
        if (measurementQueue.isEmpty()) {
          break; // nothing more to send
        }

        // Peek the oldest entry WITHOUT removing it
        Measurement frontItem;
        if (!measurementQueue.peek(&frontItem)) {
          break; // queue might be empty or error
        }

        // Convert ms to seconds
        float timeSec = frontItem.timeSinceStart / 1000.0f;

        // Build JSON
        StaticJsonDocument<256> doc;
        doc["time"]     = timeSec;            // in seconds
        doc["depth"]    = frontItem.depth;
        doc["pressure"] = frontItem.pressure;
        doc["company"]  = frontItem.companyNum;

        String payload;
        serializeJson(doc, payload);

        // Attempt HTTP POST
        if (laptopIpAddress.isEmpty()) {
          Serial.println("No laptop IP, can't send. Breaking out...");
          break;
        }

        String postUrl = "http://" + laptopIpAddress + ":8000/depth";
        http.begin(postUrl);
        http.addHeader("Content-Type", "application/json");
        int code = http.POST(payload);

        if (code == 200) {
          // Check response
          String resp = http.getString();
          if (resp.indexOf("DATARECEIVED") >= 0 || resp.indexOf("OK") >= 0) {
            // Transmission successful => remove from queue
            measurementQueue.drop();
            Serial.println("Packet sent OK. (Popped from queue)");

            // Flash LED BLUE for 1 second
            setStripColor(0, 0, 255);
            vTaskDelay(1000 / portTICK_PERIOD_MS);
          }
          else {
            // Unexpected server response => do NOT pop, stop sending
            Serial.println("Server response not recognized. Stopping batch.");
            http.end();
            break;
          }
        }
        else {
          // HTTP failure => do NOT pop
          Serial.printf("HTTP POST failed, code = %d\n", code);
          http.end();
          break;
        }

        http.end();
      } // end batch for-loop

      // ******** 1-SECOND DELAY AFTER SENDING THE BATCH ********
      vTaskDelay(1000 / portTICK_PERIOD_MS);
    }

    // 4) LED color based on state
    if (!wifiFlag) {
      // WiFi not connected or RSSI too low => RED
      setStripColor(255, 0, 0);
    } else {
      // WiFi good
      if (measurementQueue.isEmpty()) {
        setStripColor(0, 255, 0);    // GREEN if queue empty
      } else {
        setStripColor(255, 255, 0); // YELLOW if queue not empty
      }
    }

    vTaskDelay(50 / portTICK_PERIOD_MS);
  }
}

// -------------------- SETUP --------------------
void setup() {
  Serial.begin(115200);

  // NeoPixel power pin
  pinMode(NEOPIXEL_POWER_PIN, OUTPUT);
  digitalWrite(NEOPIXEL_POWER_PIN, HIGH);

  strip.begin();
  strip.setBrightness(50);
  setStripColor(255, 0, 0);  // Red initially

  // Start WiFi (blocking in setup)
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
  server.begin();
  Serial.println("HTTP server started on port 80");

  // Initialize the depth sensor
  Wire.begin();
  sensor.setModel(MS5837::MS5837_02BA);
  if (!sensor.init()) {
    Serial.println("MS5837 sensor init failed!");
  }
  // Set fluid density for saltwater
  sensor.setFluidDensity(1029);

  // Initialize wifiFlag based on RSSI
  if (WiFi.status() == WL_CONNECTED) {
    long rssi = WiFi.RSSI();
    wifiFlag = (rssi >= RSSI_THRESHOLD);
  }

  // -------------------- CREATE TASKS --------------------
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
  // Everything is handled in FreeRTOS tasks
  delay(1000);
}
