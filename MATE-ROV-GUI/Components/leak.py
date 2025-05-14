from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QColor, QPalette
import time

class LeakSensor(QWidget):
    """Widget to display leak sensor data"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.leak_detected = False
        self.sensor_reading = 0
        self.last_update = 0
        self.setupUI()
        
    def setupUI(self):
        """Set up the UI components"""
        layout = QVBoxLayout(self)
        self.setStyleSheet("background-color: #2f3542;")
        
        # Add title
        title_label = QLabel("Leak Detection System")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold; padding: 10px;")
        layout.addWidget(title_label)
        
        # Add status indicator
        self.status_indicator = QLabel("NO LEAK DETECTED")
        self.status_indicator.setAlignment(Qt.AlignCenter)
        self.status_indicator.setStyleSheet(
            "color: white; background-color: #27ae60; font-weight: bold; padding: 10px;"
        )
        layout.addWidget(self.status_indicator)
        
        # Add sensor reading display
        self.reading_label = QLabel("Sensor Reading:")
        self.reading_label.setStyleSheet("color: white;")
        layout.addWidget(self.reading_label)
        
        # Progress bar for visual representation of sensor reading
        self.reading_bar = QProgressBar()
        self.reading_bar.setRange(0, 100)
        self.reading_bar.setValue(0)
        self.reading_bar.setTextVisible(True)
        self.reading_bar.setFormat("%v%")
        palette = QPalette()
        palette.setColor(QPalette.Highlight, QColor("#27ae60"))  # Green color when no leak
        self.reading_bar.setPalette(palette)
        layout.addWidget(self.reading_bar)
        
        # Last updated timestamp
        self.last_updated_label = QLabel("Last updated: Never")
        self.last_updated_label.setStyleSheet("color: white;")
        self.last_updated_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.last_updated_label)
        
        # Status message
        self.status_message = QLabel("System operational")
        self.status_message.setAlignment(Qt.AlignCenter)
        self.status_message.setStyleSheet("color: white;")
        layout.addWidget(self.status_message)
        
        # Add some stretching to make the layout look better
        layout.addStretch(1)
        
    @pyqtSlot(dict)
    def update_status(self, leak_data):
        """Update the widget with new leak sensor data"""
        if not leak_data:
            return
        print(f"LEAK WIDGET: Received update: {leak_data}")  # Add debug print
        self.leak_detected = leak_data.get("leak_detected", False)
        self.sensor_reading = int(leak_data.get("reading", 0) * 100)  # Convert to percentage
        self.last_update = time.time()
        
        # Update UI based on leak status
        if self.leak_detected:
            self.status_indicator.setText("LEAK DETECTED!")
            self.status_indicator.setStyleSheet(
                "color: white; background-color: #e74c3c; font-weight: bold; padding: 10px;"
            )
            self.status_message.setText("IMMEDIATE ACTION REQUIRED")
            # Set progress bar color to red
            palette = QPalette()
            palette.setColor(QPalette.Highlight, QColor("#e74c3c"))
            self.reading_bar.setPalette(palette)
        else:
            self.status_indicator.setText("NO LEAK DETECTED")
            self.status_indicator.setStyleSheet(
                "color: white; background-color: #27ae60; font-weight: bold; padding: 10px;"
            )
            self.status_message.setText("System operational")
            # Set progress bar color to green
            palette = QPalette()
            palette.setColor(QPalette.Highlight, QColor("#27ae60"))
            self.reading_bar.setPalette(palette)
        
        # Update reading display
        self.reading_bar.setValue(self.sensor_reading)
        self.reading_label.setText(f"Sensor Reading: {self.sensor_reading}%")
        
        # Update timestamp
        self.last_updated_label.setText(f"Last updated: {time.strftime('%H:%M:%S')}")
    
    @pyqtSlot(dict)
    def update_from_telemetry(self, telemetry_data):
        """Extract leak data from telemetry"""
        if not telemetry_data:
            return
        
        # Check if leak sensor data is in the telemetry
        if "leak_sensor" in telemetry_data:
            self.update_status(telemetry_data["leak_sensor"])
    
    @pyqtSlot(dict)
    def update_from_emergency(self, emergency_data):
        """Handle emergency leak alerts"""
        print(f"EMERGENCY RECEIVED: {emergency_data}")  # Debug print
        if not emergency_data:
            return
            
        # Check if this is a leak emergency
        if emergency_data.get("type") == "leak_detected":
            self.leak_detected = True
            self.sensor_reading = 100  # Assume worst case
            self.last_update = time.time()
            
            # Update UI to show emergency
            self.status_indicator.setText("EMERGENCY: LEAK DETECTED!")
            self.status_indicator.setStyleSheet(
                "color: white; background-color: #e74c3c; font-weight: bold; padding: 10px;"
            )
            self.status_message.setText(emergency_data.get("message", "IMMEDIATE ACTION REQUIRED"))
            
            # Set progress bar to full and red
            palette = QPalette()
            palette.setColor(QPalette.Highlight, QColor("#e74c3c"))
            self.reading_bar.setPalette(palette)
            self.reading_bar.setValue(100)
            
            # Update timestamp
            self.last_updated_label.setText(f"Emergency alert: {time.strftime('%H:%M:%S')}")