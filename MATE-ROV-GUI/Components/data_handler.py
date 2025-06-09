from PyQt5.QtCore import QObject, pyqtSignal, QThread
import socket
import json
import time
import logging

# Make sure your DataSignals class has this signal:
class DataSignals(QObject):
    """Signals for data updates"""
    depth_update = pyqtSignal(dict)
    imu_update = pyqtSignal(dict)
    leak_update = pyqtSignal(dict)  # Make sure this exists
    emergency_update = pyqtSignal(dict)
    telemetry_received = pyqtSignal(dict)

class DataHandler(QThread):
    """Handles data reception from the ROV and distributes it to UI components"""
    
    def __init__(self, ip="192.168.50.41", port=8001):
        super().__init__()
        self.ip = ip
        self.port = port
        self.running = False
        self.signals = DataSignals()
        self.socket = None
        
    def run(self):
        """Main thread function that listens for data"""
        self.running = True
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("0.0.0.0", self.port))
        self.socket.settimeout(0.5)
        
        logging.info(f"DataHandler listening for telemetry on UDP port {self.port}")
        
        while self.running:
            try:
                data, addr = self.socket.recvfrom(8001)
                telemetry = json.loads(data.decode('utf-8'))
                
                # Emit the entire telemetry packet
                self.signals.telemetry_received.emit(telemetry)
                
                # Emit specific data types
                if "depth" in telemetry:
                    self.signals.depth_update.emit(telemetry["depth"])
                
                if "imu" in telemetry:
                    self.signals.imu_update.emit(telemetry["imu"])
                    
                # Handle leak sensor data
                if "leak_sensor" in telemetry:
                    self.signals.leak_update.emit(telemetry["leak_sensor"])
                
                # Handle emergency alerts
                if "emergency" in telemetry and telemetry["emergency"] is True:
                    self.signals.emergency_update.emit(telemetry)
                    
            except socket.timeout:
                pass
            except json.JSONDecodeError:
                logging.warning("Received invalid JSON data")
            except Exception as e:
                logging.error(f"Error in data handler: {e}")
                time.sleep(1)
                
    def stop(self):
        """Stop the data handler thread"""
        self.running = False
        if self.socket:
            self.socket.close()