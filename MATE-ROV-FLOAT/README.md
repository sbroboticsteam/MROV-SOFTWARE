# MROV-FLOAT

## Underwater Float Data Collection System

This project implements a data collection system for an underwater float device. The system consists of an ESP32 microcontroller with a depth sensor in the float that communicates wirelessly with a laptop on the surface.

## Features

* Real-time depth and pressure data collection
* Wireless data transmission via WiFi
* Data persistence during connection loss with automatic retransmission
* Variable sampling rates for velocity testing
* Visual status indicator via onboard NeoPixel LED
* Graphical data visualization on the surface laptop
* Multiple operation modes (normal and velocity testing)

## System Requirements

### Hardware

* ESP32 microcontroller board
* MS5837 depth/pressure sensor (Blue Robotics)
* NeoPixel LED
* Laptop with WiFi connectivity

### Software

* Arduino IDE (1.8.13 or newer)
* Python 3.7+ with the following libraries:
  * matplotlib
  * requests
  * socket

## Installation

### 1. Arduino Libraries

1. Download the following libraries as ZIP files:
   * [MS5837 Library](vscode-file://vscode-app/c:/Users/ruthv/AppData/Local/Programs/Microsoft%20VS%20Code/resources/app/out/vs/code/electron-sandbox/workbench/workbench.html)
   * [cppQueue Library](vscode-file://vscode-app/c:/Users/ruthv/AppData/Local/Programs/Microsoft%20VS%20Code/resources/app/out/vs/code/electron-sandbox/workbench/workbench.html)
   * [ArduinoJson Library](vscode-file://vscode-app/c:/Users/ruthv/AppData/Local/Programs/Microsoft%20VS%20Code/resources/app/out/vs/code/electron-sandbox/workbench/workbench.html)
   * [Adafruit NeoPixel Library](vscode-file://vscode-app/c:/Users/ruthv/AppData/Local/Programs/Microsoft%20VS%20Code/resources/app/out/vs/code/electron-sandbox/workbench/workbench.html)
2. In the Arduino IDE, go to **Sketch > Include Library > Add .ZIP Library** and select each downloaded ZIP file.

### 2. ESP32 Setup

1. Install ESP32 board support in Arduino IDE:

   * Go to **File > Preferences**
   * Add `https://dl.espressif.com/dl/package_esp32_index.json` to "Additional Board Manager URLs"
   * Go to **Tools > Board > Boards Manager**
   * Search for ESP32 and install the package
2. Open `ESP32.ino` from the [ESP32](vscode-file://vscode-app/c:/Users/ruthv/AppData/Local/Programs/Microsoft%20VS%20Code/resources/app/out/vs/code/electron-sandbox/workbench/workbench.html) folder
3. Select the correct board and port:

   * **Tools > Board > ESP32 Arduino > ESP32 Dev Module**
   * Select the appropriate COM port under **Tools > Port**
4. Modify WiFi credentials if necessary:

   **#define** WIFI_SSID       **"SBRT"**

   **#define** WIFI_PASSWORD   **"Robotic$3"**
5. Upload the code to your ESP32 by clicking the upload button or pressing **Ctrl+U**
6. Open the Serial Monitor ( **Tools > Serial Monitor** ) and set the baud rate to 115200 to verify the ESP32 is working properly. You should see initialization messages and the ESP32's IP address.

### 3. Laptop Software Setup

1. Install required Python libraries:

   **pip** **install** **matplotlib** **requests**
2. Navigate to the MATE-ROV-FLOAT/laptop folder

## Usage

### Starting the System

1. Open a terminal/command prompt and navigate to the MATE-ROV-FLOAT/laptop folder
2. Start the laptop server:

   **python** **surface_laptop.py**

   This will start a server on port 8000 that will receive data from the ESP32.
3. Open another terminal/command prompt and navigate to the MATE-ROV-FLOAT/laptop folder
4. Run the command interface:

   **python** **send_command.py**
5. When prompted, enter the ESP32's IP address (visible in the Arduino Serial Monitor)
6. Use the following commands to control the float:

   * `s` - Start float (begins data collection and transmission)
   * `vs` - Start velocity testing (increases data collection rate)
   * `vst` - Stop velocity testing (returns to normal data rate)
   * `st` - Stop float (halts data collection)
   * `q` - Quit the command interface

### Viewing the Data

While the system is running, data is saved to `coordinates.json` in the laptop folder. To visualize this data:

1. Open a terminal/command prompt and navigate to the MATE-ROV-FLOAT/laptop folder
2. Run the plotting script:

   **python** **plot.py**
3. This will display graphs of depth, pressure, and velocity over time.

## Project Structure

* `/esp32/ESP32/` - Main ESP32 code for autonomous operation
* `/esp32/VelocityTest/` - Enhanced code with variable sampling rates for velocity testing
* `/laptop/surface_laptop.py` - Server for receiving data from ESP32
* `/laptop/send_command.py` - Command interface for controlling the float
* `/laptop/plot.py` - Data visualization tool

## LED Status Indicators

* **Red** : WiFi disconnected or signal below threshold, or system not started
* **Yellow** : WiFi connected, system running, data in queue waiting to be sent
* **Green** : WiFi connected, system running, queue empty (all data sent)
* **Blue** (flash): Data packet successfully sent

## Troubleshooting

* **ESP32 not connecting to WiFi** : Verify the SSID and password are correct
* **Data not being received** : Ensure the laptop and ESP32 are on the same network
* **Connection errors** : Check that firewalls aren't blocking communication on port 8000
* **Sensor errors** : Verify the sensor is correctly wired to the ESP32
* **LED stays red** : Check WiFi connection and RSSI threshold
* **Queue filling up** : Check laptop server is running and receiving data correctly

## Technical Details

* The ESP32 runs two concurrent tasks using FreeRTOS:
  * Core 0: WiFi connection monitoring and HTTP server
  * Core 1: Sensor reading and data transmission
* Data is stored in a FIFO queue when WiFi connection is poor
* The system can switch between normal mode (2000ms sample rate) and velocity testing mode (20ms sample rate)
* All HTTP communication uses GET for commands and POST for data transmission

## Contact

For issues or questions, please contact Ruthvick.Bandaru@Stonybrook.edu
