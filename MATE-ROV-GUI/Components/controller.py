import sys
import os
import time
import socket
import json
import pygame
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit, QHBoxLayout, QGridLayout, QFrame
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QMutex
from PyQt5.QtGui import QColor

# Add path to arcadeDrive3 function
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'MATE-ROV-CONTROL', 'src')))
try:
    from arcadeDrive import arcadeDrive3
except ImportError:
    print("Error: Could not import arcadeDrive3. Using placeholder function.")
    def arcadeDrive3(x, y, rx, rT, lT):
        return [0.0] * 8  # Return 8 zeros as placeholder

class ControllerThread(QThread):
    """Thread that reads Xbox controller input and emits updates"""
    controllerUpdate = pyqtSignal(list)
    statusUpdate = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.joystick = None
        self.controller_values = [0.0] * 5  # x, y, rx, rT, lT
    
    def run(self):
        self.running = True
        try:
            pygame.init()
            pygame.joystick.init()
            
            if pygame.joystick.get_count() == 0:
                self.statusUpdate.emit("No controller detected")
                self.running = False
                return
                
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.statusUpdate.emit(f"Connected to {self.joystick.get_name()}")
            
            # Apply deadzone function
            def apply_deadzone(value, deadzone=0.1):
                if abs(value) < deadzone:
                    return 0
                return value
            
            while self.running:
                pygame.event.pump()  # Process events
                
                # Read joystick values
                x = apply_deadzone(self.joystick.get_axis(0))  # Left stick X
                y = apply_deadzone(-self.joystick.get_axis(1))  # Left stick Y (inverted)
                rx = apply_deadzone(self.joystick.get_axis(2))  # Right stick X
                rT = (self.joystick.get_axis(5) + 1) / 2.0  # Right trigger (0 to 1)
                lT = (self.joystick.get_axis(4) + 1) / 2.0  # Left trigger (0 to 1)
                
                # Only update if values changed significantly
                new_values = [x, y, rx, rT, lT]
                if any(abs(new_values[i] - self.controller_values[i]) > 0.01 for i in range(5)):
                    self.controller_values = new_values
                    # Calculate motor values using arcadeDrive3
                    motor_values = arcadeDrive3(x, y, rx, rT, lT)
                    self.controllerUpdate.emit(motor_values)
                
                time.sleep(0.02)  # ~50Hz update rate
                
        except Exception as e:
            self.statusUpdate.emit(f"Controller error: {e}")
        finally:
            pygame.quit()
            self.statusUpdate.emit("Controller thread stopped")
    
    def stop(self):
        self.running = False
        self.wait()

class SocketThread(QThread):
    """Thread that manages socket connection to the Jetson"""
    connected = pyqtSignal(bool)
    statusUpdate = pyqtSignal(str)
    
    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.motor_values = None
        self.mutex = QMutex()
        self.connected_flag = False
    
    def run(self):
        self.running = True
        retry_delay = 2  # seconds between connection attempts
        
        while self.running:
            try:
                if not self.connected_flag:
                    self.statusUpdate.emit(f"Connecting to {self.host}:{self.port}...")
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.settimeout(5)  # 5 second timeout for connection
                    self.socket.connect((self.host, self.port))
                    self.socket.settimeout(1)  # Shorter timeout for send/recv operations
                    self.connected_flag = True
                    self.connected.emit(True)
                    self.statusUpdate.emit(f"Connected to {self.host}:{self.port}")
                
                # Only send if we have motor values
                self.mutex.lock()
                current_values = self.motor_values
                self.mutex.unlock()
                
                if current_values is not None and self.connected_flag:
                    try:
                        # Format data as expected by 8motorcode.py
                        json_data = json.dumps({"motor_values": current_values})
                        self.socket.sendall(json_data.encode('utf-8'))
                        
                        # Optional: Check for response
                        # response = self.socket.recv(1024).decode('utf-8')
                        # self.statusUpdate.emit(f"Response: {response}")
                    except socket.timeout:
                        # Just a timeout on send/recv, not fatal
                        pass
                    except socket.error as e:
                        # Connection lost
                        self.statusUpdate.emit(f"Socket error: {e}")
                        self.connected_flag = False
                        self.connected.emit(False)
                        self.socket.close()
                
                time.sleep(0.05)  # Slight delay to prevent tight loop
                
            except socket.error as e:
                self.statusUpdate.emit(f"Socket error: {e}")
                self.connected_flag = False
                self.connected.emit(False)
                if self.socket:
                    self.socket.close()
                time.sleep(retry_delay)  # Wait before retrying
    
    def update_motor_values(self, values):
        self.mutex.lock()
        self.motor_values = values
        self.mutex.unlock()
    
    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()
        self.wait()

class ControllerSender(QWidget):
    """Widget for sending controller inputs to a remote Jetson"""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Default Jetson connection settings
        self.jetson_ip = "192.168.0.160"  # Default from 8motorcode.py
        self.jetson_port = 4891
        
        # Setup UI components
        self.setup_ui()
        
        # Initialize controller and socket threads
        self.controller_thread = None
        self.socket_thread = None
        
        # Start controller reading immediately
        self.start_controller_thread()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Title
        title = QLabel("Controller Sender")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Connection settings frame
        conn_frame = QFrame()
        conn_frame.setFrameShape(QFrame.StyledPanel)
        conn_frame.setStyleSheet("background-color: #f0f0f0;")
        conn_layout = QGridLayout()
        
        # IP input
        ip_label = QLabel("Jetson IP:")
        self.ip_input = QLineEdit(self.jetson_ip)
        
        # Port input
        port_label = QLabel("Port:")
        self.port_input = QLineEdit(str(self.jetson_port))
        self.port_input.setMaximumWidth(80)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        
        # Add to grid
        conn_layout.addWidget(ip_label, 0, 0)
        conn_layout.addWidget(self.ip_input, 0, 1)
        conn_layout.addWidget(port_label, 0, 2)
        conn_layout.addWidget(self.port_input, 0, 3)
        conn_layout.addWidget(self.connect_btn, 0, 4)
        
        conn_frame.setLayout(conn_layout)
        layout.addWidget(conn_frame)
        
        # Status display
        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Controller values display
        self.controller_display = QLabel("Controller values: N/A")
        self.controller_display.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.controller_display)
        
        # Motor values display
        self.motor_display = QLabel("Motor values: N/A")
        self.motor_display.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.motor_display)
        
        # Set main layout
        self.setLayout(layout)
    
    def start_controller_thread(self):
        """Initialize and start the controller thread"""
        if self.controller_thread is None or not self.controller_thread.isRunning():
            self.controller_thread = ControllerThread()
            self.controller_thread.controllerUpdate.connect(self.on_controller_update)
            self.controller_thread.statusUpdate.connect(self.update_status)
            self.controller_thread.start()
    
    def toggle_connection(self):
        """Connect or disconnect from the Jetson"""
        if self.socket_thread is None or not self.socket_thread.isRunning():
            # Start connection
            try:
                host = self.ip_input.text()
                port = int(self.port_input.text())
                self.socket_thread = SocketThread(host, port)
                self.socket_thread.connected.connect(self.on_connection_change)
                self.socket_thread.statusUpdate.connect(self.update_status)
                self.socket_thread.start()
                self.connect_btn.setText("Disconnect")
                self.ip_input.setEnabled(False)
                self.port_input.setEnabled(False)
            except ValueError:
                self.update_status("Invalid port number")
        else:
            # Stop connection
            if self.socket_thread and self.socket_thread.isRunning():
                self.socket_thread.stop()
                self.socket_thread = None
                self.connect_btn.setText("Connect")
                self.ip_input.setEnabled(True)
                self.port_input.setEnabled(True)
                self.update_status("Disconnected")
    
    def on_controller_update(self, motor_values):
        """Handle controller updates from the thread"""
        # Update UI with motor values
        rounded_values = [round(val, 2) for val in motor_values]
        self.motor_display.setText(f"Motor values: {rounded_values}")
        
        # Send values to socket thread if connected
        if self.socket_thread and self.socket_thread.isRunning():
            self.socket_thread.update_motor_values(motor_values)
    
    def on_connection_change(self, connected):
        """Handle connection state changes"""
        if connected:
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setStyleSheet("background-color: #f44336; color: white;")
        else:
            self.connect_btn.setText("Connect")
            self.connect_btn.setStyleSheet("")
    
    def update_status(self, message):
        """Update the status display"""
        self.status_label.setText(f"Status: {message}")
        print(f"[ControllerSender] {message}")
    
    def closeEvent(self, event):
        """Clean up threads when widget is closed"""
        if self.controller_thread and self.controller_thread.isRunning():
            self.controller_thread.stop()
        
        if self.socket_thread and self.socket_thread.isRunning():
            self.socket_thread.stop()
        
        super().closeEvent(event)