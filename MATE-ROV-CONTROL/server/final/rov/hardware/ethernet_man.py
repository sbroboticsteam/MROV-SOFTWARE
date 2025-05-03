import socket
import threading
import time
import json
import logging
from typing import Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

# --------------------------- Ethernet Manager Class ---------------------------
class EthernetManager:
    """Manages all network communications for the ROV using UDP"""
    def __init__(self, control_ip: str = '192.168.1.237', control_port: int = 4891):
        self.control_ip = control_ip
        self.control_port = control_port
        self.control_socket = None
        self.connected = False
        self.control_thread = None
        self.running = False
        self.control_callback = None
        self.last_heartbeat = 0
        self.client_address = None  # Store the most recent client's address
        logger.info(f"Ethernet manager initialized with UDP control IP: {control_ip}:{control_port}")
    
    def start_control_server(self) -> bool:
        try:
            # Create UDP socket instead of TCP
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.control_socket.bind((self.control_ip, self.control_port))
            self.control_socket.settimeout(1.0)
            self.running = True
            self.control_thread = threading.Thread(target=self._control_listener, daemon=True)
            self.control_thread.start()
            logger.info(f"UDP control server started on {self.control_ip}:{self.control_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start UDP control server: {e}")
            return False
    
    def _control_listener(self) -> None:
        logger.info("UDP control listener thread started")
        while self.running:
            try:
                # For UDP, recvfrom returns data and client address
                data, client_address = self.control_socket.recvfrom(1024)
                if not data:
                    continue
                
                # Store client address for sending responses
                self.client_address = client_address
                self.connected = True
                self.last_heartbeat = time.time()
                
                # Process the received data
                self._process_control_data(data)
                
            except socket.timeout:
                # Check for client timeout (5 seconds without data)
                if self.connected and time.time() - self.last_heartbeat > 5.0:
                    logger.info("Client connection timed out")
                    self.connected = False
                    self.client_address = None
            except Exception as e:
                if self.running:
                    logger.error(f"UDP control listener error: {e}")
                time.sleep(0.5)
    
    def _process_control_data(self, data):
        try:
            command_data = json.loads(data.decode('utf-8'))
            if self.control_callback:
                # Call the callback with the parsed data
                self.control_callback(command_data)
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            logger.error(f"Error processing control data: {e}")

    def _send_data(self, data):
        try:
            # For UDP, we need to sendto a specific address
            if self.connected and self.client_address:
                self.control_socket.sendto(data, self.client_address)
        except Exception as e:
            logger.error(f"Error sending UDP data: {e}")
            self.connected = False

    def set_control_callback(self, callback) -> None:
        self.control_callback = callback
    
    def send_telemetry(self, telemetry_data: dict) -> bool:
        """Send telemetry data to the connected client"""
        try:
            if self.connected and self.client_address:
                json_data = json.dumps(telemetry_data).encode('utf-8')
                self.control_socket.sendto(json_data, self.client_address)
                return True
            return False
        except Exception as e:
            logger.error(f"Error sending telemetry: {e}")
            self.connected = False
            return False
    
    def shutdown(self) -> None:
        """Safely shutdown the ethernet manager."""
        self.running = False
        if hasattr(self, 'control_thread') and self.control_thread:
            self.control_thread.join(timeout=1.0)
        if hasattr(self, 'control_socket') and self.control_socket:
            try:
                self.control_socket.close()
            except:
                pass
        logger.info("Ethernet manager shutdown complete")
