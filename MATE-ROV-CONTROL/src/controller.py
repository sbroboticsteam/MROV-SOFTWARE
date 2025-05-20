import sys
import os
import time
import socket
import json
import pygame
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit, QHBoxLayout, QFrame
from PyQt5.QtCore import QThread, pyqtSignal, Qt

class ControllerThread(QThread):
    """Reads raw controller input and emits the values"""
    dataUpdate = pyqtSignal(dict)
    statusUpdate = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.running = False
        
    def run(self):
        try:
            # Initialize pygame for controller input
            pygame.init()
            pygame.joystick.init()
            
            # Check if any controllers are connected
            if pygame.joystick.get_count() == 0:
                self.statusUpdate.emit("No controller detected")
                return
                
            # Initialize the first controller
            joystick = pygame.joystick.Joystick(0)
            joystick.init()
            self.statusUpdate.emit(f"Connected to controller: {joystick.get_name()}")
            
            self.running = True
            
            # Create previous state to track changes
            prev_inputs = None
            
            # Main loop to read controller input
            while self.running:
                pygame.event.pump()  # Process events
                
                # Read all controller inputs
                num_axes = joystick.get_numaxes()
                num_buttons = joystick.get_numbuttons()
                num_hats = joystick.get_numhats()
                
                # Get all axis values
                axes = [joystick.get_axis(i) for i in range(num_axes)]
                
                # Apply deadzone to joystick axes (typically first 4 are joysticks)
                # This keeps the same raw data but prevents small noise/drift
                deadzone = 0.1
                for i in range(min(4, num_axes)):
                    if abs(axes[i]) < deadzone:
                        axes[i] = 0.0
                
                # Get all button values (1 for pressed, 0 for not pressed)
                buttons = [joystick.get_button(i) for i in range(num_buttons)]
                
                # Get all hat values (typically returns tuples like (0,0), (0,1), etc.)
                hats = [joystick.get_hat(i) for i in range(num_hats)]
                
                # Create input data dictionary
                inputs = {
                    "axes": axes,
                    "buttons": buttons,
                    "hats": hats
                }
                
                # Only send updates when values change (to reduce network traffic)
                if inputs != prev_inputs:
                    self.dataUpdate.emit(inputs)
                    prev_inputs = inputs.copy()  # Make a copy to prevent reference issues
                
                # Small delay to prevent high CPU usage
                time.sleep(0.02)  # 50Hz update rate
                
        except Exception as e:
            self.statusUpdate.emit(f"Controller error: {str(e)}")
        finally:
            # Clean up pygame
            pygame.quit()
            self.statusUpdate.emit("Controller disconnected")
    
    def stop(self):
        """Stop the controller thread"""
        self.running = False
        self.wait()

class ControllerSender(QWidget):
    """Widget for sending raw controller data to the Jetson"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()
        
        # Connection info
        self.socket = None
        self.connected = False
        
        # Start controller thread
        self.controller_thread = ControllerThread()
        self.controller_thread.dataUpdate.connect(self.on_data_update)
        self.controller_thread.statusUpdate.connect(self.update_status)
        self.controller_thread.start()
    
    def setupUI(self):
        """Set up the widget UI"""
        main_layout = QVBoxLayout()
        
        # Connection controls
        conn_frame = QFrame()
        conn_frame.setFrameShape(QFrame.StyledPanel)
        conn_layout = QHBoxLayout(conn_frame)
        
        # IP address input
        self.ip_input = QLineEdit("192.168.0.160")  # Default Jetson IP
        ip_label = QLabel("Jetson IP:")
        
        # Port input
        self.port_input = QLineEdit("4891")  # Default port
        port_label = QLabel("Port:")
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        
        # Add widgets to connection layout
        conn_layout.addWidget(ip_label)
        conn_layout.addWidget(self.ip_input)
        conn_layout.addWidget(port_label)
        conn_layout.addWidget(self.port_input)
        conn_layout.addWidget(self.connect_btn)
        
        # Status display
        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        # Input displays
        self.axes_label = QLabel("Axes: [waiting for input]")
        self.buttons_label = QLabel("Buttons: [waiting for input]")
        self.hats_label = QLabel("Hats: [waiting for input]")
        
        # Explanation label
        self.info_label = QLabel(
            "Sends raw controller data to the Jetson.\n"
            "The Jetson will handle motor calculations."
        )
        self.info_label.setAlignment(Qt.AlignCenter)
        
        # Add widgets to main layout
        main_layout.addWidget(conn_frame)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.axes_label)
        main_layout.addWidget(self.buttons_label)
        main_layout.addWidget(self.hats_label)
        main_layout.addWidget(self.info_label)
        
        # Add some spacing
        main_layout.addStretch()
        
        self.setLayout(main_layout)
    
    def toggle_connection(self):
        """Connect or disconnect from the Jetson"""
        if not self.connected:
            self.connect_to_jetson()
        else:
            self.disconnect_from_jetson()
    
    def connect_to_jetson(self):
        """Establish connection to the Jetson"""
        try:
            # Get IP and port from input fields
            ip = self.ip_input.text()
            port = int(self.port_input.text())
            
            # Create socket and connect
            self.update_status(f"Connecting to {ip}:{port}...")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(3)  # 3 second timeout
            self.socket.connect((ip, port))
            
            # Update UI
            self.connected = True
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setStyleSheet("background-color: #f44336; color: white;")
            self.ip_input.setEnabled(False)
            self.port_input.setEnabled(False)
            self.update_status(f"Connected to {ip}:{port}")
            
        except socket.timeout:
            self.update_status("Connection timed out")
            if self.socket:
                self.socket.close()
                self.socket = None
        except socket.error as e:
            self.update_status(f"Connection error: {str(e)}")
            if self.socket:
                self.socket.close()
                self.socket = None
        except ValueError:
            self.update_status("Invalid port number")
    
    def disconnect_from_jetson(self):
        """Close the connection to the Jetson"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            finally:
                self.socket = None
        
        # Update UI
        self.connected = False
        self.connect_btn.setText("Connect")
        self.connect_btn.setStyleSheet("")
        self.ip_input.setEnabled(True)
        self.port_input.setEnabled(True)
        self.update_status("Disconnected")
    
    def on_data_update(self, data):
        """Handle controller data updates"""
        # Update the UI with current values
        if "axes" in data:
            # Round values for display
            axes = [round(v, 2) for v in data["axes"]]
            self.axes_label.setText(f"Axes: {axes}")
            
        if "buttons" in data:
            self.buttons_label.setText(f"Buttons: {data['buttons']}")
            
        if "hats" in data:
            self.hats_label.setText(f"Hats: {data['hats']}")
        
        # Send data to Jetson if connected
        if self.connected and self.socket:
            try:
                # Convert data to JSON and send
                # Depending on what your Jetson code expects, you might need to modify the structure
                json_data = json.dumps({"controller_data": data})
                self.socket.sendall(json_data.encode('utf-8') + b'\n')  # Add newline as terminator
            except socket.error as e:
                self.update_status(f"Send error: {str(e)}")
                self.disconnect_from_jetson()
    
    def update_status(self, message):
        """Update the status display"""
        self.status_label.setText(f"Status: {message}")
        print(f"[ControllerSender] {message}")
    
    def closeEvent(self, event):
        """Clean up when widget is closed"""
        # Stop controller thread
        if self.controller_thread and self.controller_thread.isRunning():
            self.controller_thread.stop()
        
        # Close connection
        self.disconnect_from_jetson()
        
        # Accept the close event
        event.accept()