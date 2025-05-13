from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QProgressBar
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QPalette
import time

class LeakSensor(QWidget):
    """Widget for displaying leak sensor status and alerts"""

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.leak_detected = False
        self.last_update_time = 0
        
    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Title
        title = QLabel("Leak Detection System")
        title.setStyleSheet("background-color: #2C3E50; color: white; padding: 5px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Main content
        content_layout = QVBoxLayout()
        
        # Status indicator
        self.status_label = QLabel("NO LEAK DETECTED")
        self.status_label.setStyleSheet("background-color: #27AE60; color: white; padding: 15px; border-radius: 5px; font-weight: bold; font-size: 16px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.status_label)
        
        # Sensor value
        self.sensor_layout = QVBoxLayout()
        self.sensor_label = QLabel("Sensor Reading:")
        self.sensor_label.setAlignment(Qt.AlignLeft)
        self.sensor_layout.addWidget(self.sensor_label)
        
        # Progress bar for visual representation
        self.sensor_bar = QProgressBar()
        self.sensor_bar.setRange(0, 100)
        self.sensor_bar.setValue(0)
        self.sensor_bar.setTextVisible(True)
        self.sensor_bar.setFormat("%v%")
        self.sensor_layout.addWidget(self.sensor_bar)
        content_layout.addLayout(self.sensor_layout)
        
        # Last updated time
        self.time_label = QLabel("Last updated: Never")
        self.time_label.setAlignment(Qt.AlignRight)
        content_layout.addWidget(self.time_label)
        
        # Status info
        self.status_info = QLabel("System operational")
        self.status_info.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.status_info)
        
        container = QWidget()
        container.setStyleSheet("background-color: #ECF0F1; border-radius: 5px;")
        container.setLayout(content_layout)
        layout.addWidget(container)
        
    @pyqtSlot(dict)
    def update_from_telemetry(self, telemetry):
        """Update the leak status from telemetry data"""
        if 'depth' in telemetry and 'leak_sensor' in telemetry:
            self.update_status(telemetry['leak_sensor'])
            
    @pyqtSlot(dict)
    def update_from_emergency(self, emergency_data):
        """Handle emergency notifications"""
        if emergency_data.get('type') == 'leak_detected':
            self.set_leak_detected(True)
            message = emergency_data.get('message', 'EMERGENCY: WATER LEAK DETECTED!')
            self.status_info.setText(message)
    
    def update_status(self, leak_data):
        """Update the sensor display based on leak data"""
        self.last_update_time = time.time()
        self.time_label.setText(f"Last updated: {time.strftime('%H:%M:%S')}")
        
        # Check if we have valid data
        if isinstance(leak_data, dict):
            # Update detection status
            detected = leak_data.get('detected', False)
            self.set_leak_detected(detected)
            
            # Update sensor value if provided
            if 'value' in leak_data:
                value = leak_data['value']
                threshold = leak_data.get('threshold', 500)
                
                # Scale to 0-100% for progress bar
                percent = min(100, int((value / threshold) * 100))
                self.sensor_bar.setValue(percent)
                self.sensor_label.setText(f"Sensor Reading: {value} (Threshold: {threshold})")
                
                # Set color gradient based on value
                if not detected:
                    if percent < 50:
                        color = "#27AE60"  # Green
                    elif percent < 75:
                        color = "#F39C12"  # Orange
                    else:
                        color = "#E67E22"  # Darker orange
                    
                    self.sensor_bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")
                
            # Update status info
            status_msg = leak_data.get('status_message', 'Monitoring for water ingress')
            self.status_info.setText(status_msg)
    
    def set_leak_detected(self, detected):
        """Set the leak detection status"""
        self.leak_detected = detected
        
        if detected:
            self.status_label.setText("⚠️ LEAK DETECTED ⚠️")
            self.status_label.setStyleSheet("background-color: #C0392B; color: white; padding: 15px; border-radius: 5px; font-weight: bold; font-size: 16px;")
            self.sensor_bar.setStyleSheet("QProgressBar::chunk { background: #C0392B; }")
        else:
            self.status_label.setText("NO LEAK DETECTED")
            self.status_label.setStyleSheet("background-color: #27AE60; color: white; padding: 15px; border-radius: 5px; font-weight: bold; font-size: 16px;")