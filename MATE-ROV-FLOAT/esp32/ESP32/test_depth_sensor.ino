#include <Wire.h>

// Bar02 I2C address (check datasheet for your sensor's address)
const byte sensorAddress = 0x76; //Insert Detected i2 addr

void setup() {
  Wire.begin(); // Initialize I2C
  Serial.begin(115200); // Start serial communication at 9600 baud
}

void loop() {
  Wire.beginTransmission(sensorAddress);
  // Request 3 bytes from the sensor
  Wire.requestFrom(sensorAddress, 3);
  if (Wire.available() == 3) {
    // Read the bytes if available
    byte highByte = Wire.read();
    byte midByte = Wire.read();
    byte lowByte = Wire.read();
    
    // Combine the bytes into a 24-bit number
    long pressure_raw = (long)highByte << 16 | (long)midByte << 8 | lowByte;
    
    // Convert the raw value to pressure in mbar
    double pressure_mbar = pressure_raw / 4096.0;
    
    // Print the pressure value to the serial monitor
    Serial.print("Pressure: ");
    Serial.print(pressure_mbar);
    Serial.println(" mbar");
  }
  Wire.endTransmission();
  
  delay(1000); // Wait for a second before reading again
}