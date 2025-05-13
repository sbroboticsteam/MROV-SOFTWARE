import socket
import json
import sys
import os
import time
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QFormLayout, 
                            QLineEdit, QPushButton, QLabel, QSpinBox, QDialogButtonBox, 
                            QMessageBox, QComboBox)

def get_local_ip_addresses():
    """Get all available local IP addresses"""
    ip_list = []
    try:
        # Get all network interfaces that have an IP address
        for interface in socket.getaddrinfo(socket.gethostname(), None):
            ip = interface[4][0]
            # Filter for IPv4 addresses that aren't localhost
            if not ip.startswith('127.') and ':' not in ip:
                ip_list.append(ip)
    except:
        pass
    
    # If no addresses found via hostname, try another method
    if not ip_list:
        try:
            # Create a temporary socket to determine which interface would be used for internet
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_list.append(s.getsockname()[0])
            s.close()
        except:
            pass
    
    return ip_list

class CameraSetupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Camera Stream Setup")
        self.setMinimumWidth(400)
        
        # Create layout
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # Add local IP address selector
        self.ip_combo = QComboBox()
        ip_addresses = get_local_ip_addresses()
        
        if ip_addresses:
            self.ip_combo.addItems(ip_addresses)
        else:
            self.ip_combo.addItem("127.0.0.1")
            
        form_layout.addRow("Local IP Address:", self.ip_combo)
        
        # Add ROV IP address field
        self.rov_ip = QLineEdit("192.168.1.237")  # Default ROV IP
        form_layout.addRow("ROV IP Address:", self.rov_ip)
        
        # Add camera configuration port
        self.camera_config_port = QSpinBox()
        self.camera_config_port.setRange(1000, 65535)
        self.camera_config_port.setValue(8000)  # Default port from your code
        form_layout.addRow("Camera Config Port:", self.camera_config_port)
        
        # Add port fields
        self.zed_port = QSpinBox()
        self.zed_port.setRange(1000, 65535)
        self.zed_port.setValue(5000)  # Default port
        form_layout.addRow("ZED Camera Port:", self.zed_port)
        
        self.usb0_port = QSpinBox()
        self.usb0_port.setRange(1000, 65535)
        self.usb0_port.setValue(5004)  # Default port
        form_layout.addRow("USB Camera 1 Port:", self.usb0_port)
        
        self.usb2_port = QSpinBox()
        self.usb2_port.setRange(1000, 65535)
        self.usb2_port.setValue(5005)  # Default port
        form_layout.addRow("USB Camera 2 Port:", self.usb2_port)
        
        layout.addLayout(form_layout)
        
        # Add status label
        self.status_label = QLabel("Ready to configure camera streams")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        # Add buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.setup_streams)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        
        # Config for saving
        self.config = {}
    
    def setup_streams(self):
        """Send the configuration to the ROV to start camera streams"""
        try:
            # Create connection to the ROV
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5)  # 5 second timeout
            
            # Connect to the ROV's camera configuration server
            rov_ip = self.rov_ip.text()
            camera_port = self.camera_config_port.value()
            
            self.status_label.setText(f"Connecting to ROV at {rov_ip}:{camera_port}...")
            QApplication.processEvents()
            
            client_socket.connect((rov_ip, camera_port))
            
            # Prepare configuration
            self.config = {
                "client_ip": self.ip_combo.currentText(),
                "zed_port": self.zed_port.value(),
                "usb0_port": self.usb0_port.value(),
                "usb2_port": self.usb2_port.value()
            }
            
            # Send configuration
            self.status_label.setText("Sending configuration to ROV...")
            QApplication.processEvents()
            
            client_socket.send(json.dumps(self.config).encode('utf-8'))
            
            # Receive response
            response_data = client_socket.recv(1024).decode('utf-8')
            response = json.loads(response_data)
            
            client_socket.close()
            
            if response.get("status") == "streams_started":
                self.status_label.setText("Camera streams started successfully!")
                
                # Save configuration to file
                self._save_config()
                
                QMessageBox.information(
                    self,
                    "Success",
                    f"Camera streams have been configured successfully.\n\n"
                    f"ZED Camera: {self.config['client_ip']}:{self.config['zed_port']}\n"
                    f"USB Camera 1: {self.config['client_ip']}:{self.config['usb0_port']}\n"
                    f"USB Camera 2: {self.config['client_ip']}:{self.config['usb2_port']}"
                )
                self.accept()
            else:
                error_msg = response.get("message", "Unknown error")
                self.status_label.setText(f"Error: {error_msg}")
                QMessageBox.warning(self, "Error", f"Failed to start camera streams: {error_msg}")
                
        except socket.timeout:
            self.status_label.setText("Connection timed out. Is the ROV on and connected?")
            QMessageBox.critical(self, "Connection Error", "Connection to ROV timed out")
            
        except ConnectionRefusedError:
            self.status_label.setText("Connection refused. Is the camera server running on ROV?")
            QMessageBox.critical(self, "Connection Error", "Connection to ROV refused")
            
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to setup camera streams: {str(e)}")
    
    def _save_config(self):
        """Save camera configuration to file for the camera widgets to use"""
        try:
            # Create config directory if it doesn't exist
            config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
                
            # Save configuration
            config_file = os.path.join(config_dir, 'camera_config.json')
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
                
            return True
        except Exception as e:
            print(f"Error saving camera configuration: {e}")
            return False

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = CameraSetupDialog()
    result = dialog.exec_()
    
    # If successful, print out the details
    if result == QDialog.Accepted:
        print("Camera streams configured successfully!")
        print(f"Laptop IP: {dialog.config.get('client_ip')}")
        print(f"ZED Camera Port: {dialog.config.get('zed_port')}")
        print(f"USB Camera 1 Port: {dialog.config.get('usb0_port')}")
        print(f"USB Camera 2 Port: {dialog.config.get('usb2_port')}")
        
        # This is crucial - give the ROV time to set up the streams before returning
        print("Waiting for streams to initialize...")
        time.sleep(2)
        
        # Script will exit with success
        return 0
    else:
        print("Camera stream setup cancelled")
        return 1

if __name__ == "__main__":
    sys.exit(main())