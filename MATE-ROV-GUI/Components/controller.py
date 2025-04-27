import sys
import os
import time
import socket
import json
import pygame
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout, QFrame
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QColor

class ControllerThread(QThread):
    """Thread that reads Xbox controller input and emits RAW updates"""
    controllerUpdate = pyqtSignal(dict)
    statusUpdate = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.joystick = None
    
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
            
            # Apply deadzone function for visual cleanup only
            # The raw values are still sent for processing on the Jetson
            def apply_deadzone(value, deadzone=0.1):
                if abs(value) < deadzone:
                    return 0
                return value
            
            last_data = None
            
            while self.running:
                pygame.event.pump()  # Process events
                
                # Create raw controller data dictionary
                controller_data = {
                    "axes": [self.joystick.get_axis(i) for i in range(self.joystick.get_numaxes())],
                    "buttons": [self.joystick.get_button(i) for i in range(self.joystick.get_numbuttons())],
                    "hats": [self.joystick.get_hat(i) for i in range(self.joystick.get_numhats())]
                }
                
                # Only emit if data changed
                if controller_data != last_data:
                    self.controllerUpdate.emit(controller_data)
                    last_data = controller_data.copy()
                
                time.sleep(0.02)  # ~50Hz update rate
                
        except Exception as e:
            self.statusUpdate.emit(f"Controller error: {e}")
        finally:
            pygame.quit()
            self.statusUpdate.emit("Controller thread stopped")
    
    def stop(self):
        self.running = False
        self.wait()

class BroadcastThread(QThread):
    """Thread that broadcasts controller data to the network"""
    statusUpdate = pyqtSignal(str)
    
    def __init__(self, broadcast_port=4891):
        super().__init__()
        self.running = False
        self.broadcast_port = broadcast_port
        self.controller_data = None
        self.broadcast_socket = None
        self.commands = {}  # Store commands that will be sent with next update
    
    def set_controller_data(self, data):
        # Transform raw controller data to named format
        if not data:
            return
            
        controller = {}
        
        # Map button indices to names
        button_names = ["a", "b", "x", "y", "lb", "rb", "back", "start", "l3", "r3"]
        buttons = data.get("buttons", [])
        for i, state in enumerate(buttons):
            if i < len(button_names):
                controller[button_names[i]] = state
            else:
                controller[f"button_{i}"] = state
        
        # Map axes to names
        axes = data.get("axes", [])
        if len(axes) >= 6:
            controller["left_stick_x"] = axes[0]
            controller["left_stick_y"] = axes[1]
            controller["right_stick_x"] = axes[2]
            controller["right_stick_y"] = axes[3]
            controller["left_trigger"] = (axes[4] + 1) / 2  # Convert from [-1,1] to [0,1]
            controller["right_trigger"] = (axes[5] + 1) / 2
        
        # Map D-pad (hat)
        hats = data.get("hats", [])
        if hats and len(hats) > 0:
            controller["dpad_x"] = hats[0][0]
            controller["dpad_y"] = hats[0][1]
        
        self.controller_data = controller
    
    def set_command(self, command_name, value):
        """Set a command to be sent with the next packet"""
        self.commands[command_name] = value
        
    def clear_command(self, command_name):
        """Remove a command so it won't be sent anymore"""
        if command_name in self.commands:
            del self.commands[command_name]
            
    def clear_all_commands(self):
        """Clear all commands"""
        self.commands = {}
    
    def run(self):
        self.running = True
        self.broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        target_ip = '192.168.1.237'
        self.statusUpdate.emit(f"Sending controller data to {target_ip} on port {self.broadcast_port}")
        
        try:
            while self.running:
                if self.controller_data:
                    # Build the complete packet with controller data and any commands
                    packet = {
                        "controller": self.controller_data,
                        "commands": self.commands
                    }
                    
                    # Convert to JSON and send
                    json_data = json.dumps(packet)
                    
                    try:
                        self.broadcast_socket.sendto(
                            json_data.encode('utf-8'), 
                            (target_ip, self.broadcast_port)
                        )
                    except Exception as e:
                        self.statusUpdate.emit(f"Send error: {e}")
                        time.sleep(1)  # Wait a bit longer on error
                
                time.sleep(0.05)  # 20Hz send rate
                
        except Exception as e:
            self.statusUpdate.emit(f"Send error: {e}")
        finally:
            if self.broadcast_socket:
                self.broadcast_socket.close()
            self.statusUpdate.emit("Send thread stopped")
    
    # def run(self):
    #     self.running = True
    #     self.broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    #     self.broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
    #     self.statusUpdate.emit(f"Broadcasting controller data on port {self.broadcast_port}")
        
    #     try:
    #         while self.running:
    #             if self.controller_data:
    #                 # Convert to JSON and broadcast
    #                 json_data = json.dumps(self.controller_data)
                    
    #                 # Send to broadcast address
    #                 try:
    #                     self.broadcast_socket.sendto(
    #                         json_data.encode('utf-8'), 
    #                         ('<broadcast>', self.broadcast_port)
    #                     )
    #                 except:
    #                     # Fall back to subnet broadcast if <broadcast> doesn't work
    #                     try:
    #                         # Try common subnet broadcast addresses
    #                         self.broadcast_socket.sendto(
    #                             json_data.encode('utf-8'), 
    #                             ('192.168.0.255', self.broadcast_port)
    #                         )
    #                     except Exception as e:
    #                         self.statusUpdate.emit(f"Broadcast error: {e}")
    #                         time.sleep(1)  # Wait a bit longer on error
                
    #             time.sleep(0.05)  # 20Hz broadcast rate to avoid network saturation
                
    #     except Exception as e:
    #         self.statusUpdate.emit(f"Broadcast error: {e}")
    #     finally:
    #         if self.broadcast_socket:
    #             self.broadcast_socket.close()
    #         self.statusUpdate.emit("Broadcast thread stopped")
    
    def stop(self):
        self.running = False
        if self.broadcast_socket:
            self.broadcast_socket.close()
        self.wait()

class ControllerSender(QWidget):
    """Widget for sending RAW controller inputs via UDP broadcast"""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Setup UI components
        self.setup_ui()
        
        # Initialize threads
        self.controller_thread = None
        self.broadcast_thread = None
        
        # Start controller reading immediately
        self.start_controller_thread()
        self.start_broadcast_thread()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Title
        title = QLabel("Controller Broadcaster")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Status display
        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Frame for controller values
        values_frame = QFrame()
        values_frame.setFrameShape(QFrame.StyledPanel)
        values_frame.setStyleSheet("background-color: #f0f0f0;")
        values_layout = QGridLayout(values_frame)
        
        # Labels for controller values
        self.left_stick_label = QLabel("Left Stick: (0.00, 0.00)")
        self.right_stick_label = QLabel("Right Stick: (0.00, 0.00)")
        self.triggers_label = QLabel("Triggers: L:0.00, R:0.00")
        self.buttons_label = QLabel("Buttons: None pressed")
        self.dpad_label = QLabel("D-Pad: (0, 0)")
        
        # Add to grid
        values_layout.addWidget(self.left_stick_label, 0, 0)
        values_layout.addWidget(self.right_stick_label, 1, 0)
        values_layout.addWidget(self.triggers_label, 2, 0)
        values_layout.addWidget(self.buttons_label, 3, 0)
        values_layout.addWidget(self.dpad_label, 4, 0)
        
        layout.addWidget(values_frame)
        
        # Information display
        info = QLabel("Broadcasting RAW controller data.\nMotor calculations done on Jetson.")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        
        # Set main layout
        self.setLayout(layout)
    
    def start_controller_thread(self):
        """Initialize and start the controller thread"""
        if self.controller_thread is None or not self.controller_thread.isRunning():
            self.controller_thread = ControllerThread()
            self.controller_thread.controllerUpdate.connect(self.on_controller_update)
            self.controller_thread.statusUpdate.connect(self.update_status)
            self.controller_thread.start()
    
    def start_broadcast_thread(self):
        """Initialize and start the broadcast thread"""
        if self.broadcast_thread is None or not self.broadcast_thread.isRunning():
            self.broadcast_thread = BroadcastThread()
            self.broadcast_thread.statusUpdate.connect(self.update_status)
            self.broadcast_thread.start()
    
    def on_controller_update(self, controller_data):
        """Handle controller updates from the thread"""
        # Print raw controller data to terminal
        print(f"Raw Controller Data: {json.dumps(controller_data)}")
        
        # Update broadcast thread with raw controller data
        if self.broadcast_thread and self.broadcast_thread.isRunning():
            self.broadcast_thread.set_controller_data(controller_data)
        
        # Update UI with current values
        try:
            # Standard Xbox controller mapping
            # May need adjustment for different controllers
            axes = controller_data.get("axes", [])
            buttons = controller_data.get("buttons", [])
            hats = controller_data.get("hats", [])
            
            if len(axes) >= 6:
                # Left stick
                left_x = round(axes[0], 2)
                left_y = round(-axes[1], 2)  # Inverted for display
                self.left_stick_label.setText(f"Left Stick: ({left_x}, {left_y})")
                
                # Right stick
                right_x = round(axes[2], 2)
                right_y = round(-axes[3], 2)  # Inverted for display
                self.right_stick_label.setText(f"Right Stick: ({right_x}, {right_y})")
                
                # Triggers
                left_trigger = round((axes[4] + 1) / 2, 2)
                right_trigger = round((axes[5] + 1) / 2, 2)
                self.triggers_label.setText(f"Triggers: L:{left_trigger}, R:{right_trigger}")
            
            # Buttons - show which ones are pressed
            if buttons:
                pressed = []
                button_names = ["A", "B", "X", "Y", "LB", "RB", "Back", "Start", "L3", "R3"]
                for i, pressed_state in enumerate(buttons):
                    if pressed_state:
                        if i < len(button_names):
                            pressed.append(button_names[i])
                        else:
                            pressed.append(f"B{i}")
                
                if pressed:
                    self.buttons_label.setText(f"Buttons: {', '.join(pressed)}")
                else:
                    self.buttons_label.setText("Buttons: None pressed")
            
            # D-pad (hat)
            if hats and len(hats) > 0:
                self.dpad_label.setText(f"D-Pad: {hats[0]}")
            
        except Exception as e:
            print(f"Error updating UI: {e}")
    
    def update_status(self, message):
        """Update the status display"""
        self.status_label.setText(f"Status: {message}")
        
    def closeEvent(self, event):
        """Clean up threads when widget is closed"""
        if self.controller_thread and self.controller_thread.isRunning():
            self.controller_thread.stop()
        
        if self.broadcast_thread and self.broadcast_thread.isRunning():
            self.broadcast_thread.stop()
        
        super().closeEvent(event)