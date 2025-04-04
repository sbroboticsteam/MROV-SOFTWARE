from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QLineEdit, QComboBox, QGridLayout, QGroupBox, QFormLayout)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QPalette
import socket
import requests
import json
import time
import ping3

class ConnectionMonitor(QThread):
    """Thread for monitoring connection status without freezing the UI"""
    status_update = pyqtSignal(str, str)  # (device, status)
    ping_update = pyqtSignal(str, float)  # (device, ping_time)
    
    def __init__(self, addresses=None):
        super().__init__()
        self.addresses = addresses or {}  # Dictionary of {name: ip_address}
        self.running = False
        self.timeout = 1.0  # Ping timeout in seconds
        
    def run(self):
        self.running = True
        while self.running:
            for name, ip in self.addresses.items():
                try:
                    # Try to ping the device
                    ping_time = ping3.ping(ip, timeout=self.timeout)
                    
                    if ping_time is not None and ping_time is not False:
                        self.status_update.emit(name, "Connected")
                        self.ping_update.emit(name, ping_time * 1000)  # Convert to ms
                    else:
                        self.status_update.emit(name, "Disconnected")
                        self.ping_update.emit(name, -1)  # Indicate timeout
                        
                except Exception as e:
                    self.status_update.emit(name, f"Error: {str(e)}")
                    self.ping_update.emit(name, -1)
            
            # Wait before the next check
            time.sleep(2)
    
    def update_addresses(self, addresses):
        self.addresses = addresses
        
    def stop(self):
        self.running = False
        self.wait()

class NetworkConnectionWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Network Connection")
        self.addresses = {}
        self.monitor = ConnectionMonitor(self.addresses)
        self.setupUI()
        
    def setupUI(self):
        main_layout = QVBoxLayout()
        
        # Title
        title_label = QLabel("Network Connection")
        title_label.setStyleSheet("background-color: #555555; color: white; padding: 2.5px")
        title_label.setFixedHeight(25)
        main_layout.addWidget(title_label)
        
        # Input Form for new connections
        form_group = QGroupBox("Add Connection")
        form_group.setStyleSheet("QGroupBox { background-color: #F5F5F5; border: 1px solid #ddd; }")
        form_layout = QFormLayout()
        
        self.name_input = QLineEdit()
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("8000 (Optional)")
        
        self.service_type = QComboBox()
        self.service_type.addItems(["Generic", "Router", "Camera", "Float", "ROV Controller"])
        
        form_layout.addRow("Name:", self.name_input)
        form_layout.addRow("IP Address:", self.ip_input)
        form_layout.addRow("Port:", self.port_input)
        form_layout.addRow("Type:", self.service_type)
        
        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.add_connection)
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        btn_layout.addWidget(self.connect_btn)
        
        form_layout.addRow("", btn_layout)
        form_group.setLayout(form_layout)
        main_layout.addWidget(form_group)
        
        # Status displays for all connections
        status_group = QGroupBox("Connection Status")
        status_group.setStyleSheet("QGroupBox { background-color: #F5F5F5; border: 1px solid #ddd; }")
        self.status_layout = QGridLayout()
        
        # Headers
        headers = ["Device", "IP Address", "Status", "Ping", "Actions"]
        for i, header in enumerate(headers):
            label = QLabel(header)
            label.setStyleSheet("font-weight: bold;")
            self.status_layout.addWidget(label, 0, i)
            
        status_group.setLayout(self.status_layout)
        main_layout.addWidget(status_group)
        
        # Summary status
        self.overall_status = QLabel("Not connected to any devices")
        self.overall_status.setAlignment(Qt.AlignCenter)
        self.overall_status.setStyleSheet("padding: 8px; background-color: #ffcc00; border-radius: 4px;")
        main_layout.addWidget(self.overall_status)
        
        self.setLayout(main_layout)
        
        # Start connection monitor
        self.monitor.status_update.connect(self.update_device_status)
        self.monitor.ping_update.connect(self.update_device_ping)
        self.monitor.start()
        
    def add_connection(self):
        name = self.name_input.text().strip()
        ip = self.ip_input.text().strip()
        port = self.port_input.text().strip()
        device_type = self.service_type.currentText()
        
        if not name or not ip:
            return
        
        # Format the address with port if provided
        address = ip if not port else f"{ip}:{port}"
        
        # Add to dictionary
        self.addresses[name] = ip
        
        # Update the monitor with new addresses
        self.monitor.update_addresses(self.addresses)
        
        # Add to the grid
        row = self.status_layout.rowCount()
        
        # Device name
        name_label = QLabel(f"{name} ({device_type})")
        self.status_layout.addWidget(name_label, row, 0)
        
        # IP address
        ip_label = QLabel(address)
        self.status_layout.addWidget(ip_label, row, 1)
        
        # Status
        status_label = QLabel("Checking...")
        status_label.setObjectName(f"status_{name}")
        self.status_layout.addWidget(status_label, row, 2)
        
        # Ping
        ping_label = QLabel("--")
        ping_label.setObjectName(f"ping_{name}")
        self.status_layout.addWidget(ping_label, row, 3)
        
        # Action button
        remove_btn = QPushButton("Disconnect")
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 3px 8px;
                border-radius: 2px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        remove_btn.clicked.connect(lambda: self.remove_connection(name, row))
        self.status_layout.addWidget(remove_btn, row, 4)
        
        # Clear inputs
        self.name_input.clear()
        self.ip_input.clear()
        self.port_input.clear()
        
        # Update overall status
        self.update_overall_status()
        
    def remove_connection(self, name, row):
        # Remove from addresses
        if name in self.addresses:
            del self.addresses[name]
        
        # Update the monitor
        self.monitor.update_addresses(self.addresses)
        
        # Remove widgets from grid
        for col in range(5):
            item = self.status_layout.itemAtPosition(row, col)
            if item:
                widget = item.widget()
                if widget:
                    self.status_layout.removeWidget(widget)
                    widget.deleteLater()
        
        # Update overall status
        self.update_overall_status()
    
    def update_device_status(self, device, status):
        # Find the status label for this device
        status_label = self.findChild(QLabel, f"status_{device}")
        if status_label:
            status_label.setText(status)
            
            # Set color based on status
            if status == "Connected":
                status_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                status_label.setStyleSheet("color: red; font-weight: bold;")
                
        self.update_overall_status()
    
    def update_device_ping(self, device, ping_time):
        # Find the ping label for this device
        ping_label = self.findChild(QLabel, f"ping_{device}")
        if ping_label:
            if ping_time >= 0:
                ping_label.setText(f"{ping_time:.1f} ms")
                
                # Color code based on ping time
                if ping_time < 50:
                    ping_label.setStyleSheet("color: green;")
                elif ping_time < 100:
                    ping_label.setStyleSheet("color: orange;")
                else:
                    ping_label.setStyleSheet("color: red;")
            else:
                ping_label.setText("Timeout")
                ping_label.setStyleSheet("color: red;")
    
    def update_overall_status(self):
        if not self.addresses:
            self.overall_status.setText("Not connected to any devices")
            self.overall_status.setStyleSheet("padding: 8px; background-color: #ffcc00; border-radius: 4px;")
            return
            
        connected = 0
        for device in self.addresses:
            status_label = self.findChild(QLabel, f"status_{device}")
            if status_label and status_label.text() == "Connected":
                connected += 1
                
        total = len(self.addresses)
        if connected == total:
            self.overall_status.setText(f"All devices connected ({connected}/{total})")
            self.overall_status.setStyleSheet("padding: 8px; background-color: #4CAF50; color: white; border-radius: 4px;")
        elif connected > 0:
            self.overall_status.setText(f"Partial connection ({connected}/{total} devices)")
            self.overall_status.setStyleSheet("padding: 8px; background-color: #ff9800; color: white; border-radius: 4px;")
        else:
            self.overall_status.setText(f"All devices disconnected (0/{total})")
            self.overall_status.setStyleSheet("padding: 8px; background-color: #f44336; color: white; border-radius: 4px;")
    
    def closeEvent(self, event):
        # Clean up the monitor thread when widget is closed
        if self.monitor.isRunning():
            self.monitor.stop()
        super().closeEvent(event)