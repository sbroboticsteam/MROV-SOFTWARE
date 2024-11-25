// Define the analog pin
const int analogPin = A0;

void setup() {
  // Initialize Serial Monitor
  Serial.begin(115200);
  // Wait for Serial Monitor to open
  while (!Serial) {
    delay(10);
  }
  Serial.println("Liquid Level Sensor Test");
}

void loop() {
  // Read the analog value from the sensor
  int sensorValue = analogRead(analogPin);

  // Map the analog value to a percentage (assuming a 3.3V system)
  // Adjust the min and max values based on the sensor's specifications
  // int percentage = map(sensorValue, 0, 4095, 0, 100);

  // Print the raw value and percentage to the Serial Monitor
  Serial.print("Raw Value: ");
  Serial.println(sensorValue);
  // Serial.print(" | Percentage: ");
  // Serial.print(percentage);
  // Serial.println("%");

  // Delay for readability
  delay(500);
}
