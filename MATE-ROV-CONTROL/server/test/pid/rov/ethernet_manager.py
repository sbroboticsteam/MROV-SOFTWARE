# ethernet_manager.py
import socket
import json
import threading
import time
import logging

logger = logging.getLogger("EthernetManager")

class EthernetManager:
    """Manages all network communications for the ROV"""
    def __init__(self, control_ip: str = '192.168.1.237', control_port: int = 4891):
        self.control_ip = control_ip
        self.control_port = control_port
        self.control_socket = None
        self.connected = False
        self.control_thread = None
        self.running = False
        self.control_callback = None
        self.last_heartbeat = 0
        logger.info(f"Ethernet manager initialized with control IP: {control_ip}:{control_port}")
    
    def start_control_server(self) -> bool:
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.control_socket.bind((self.control_ip, self.control_port))
            self.control_socket.listen(1)
            self.control_socket.settimeout(1.0)
            self.running = True
            self.control_thread = threading.Thread(target=self._control_listener, daemon=True)
            self.control_thread.start()
            logger.info(f"Control server started on {self.control_ip}:{self.control_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start control server: {e}")
            return False
    
    def _control_listener(self) -> None:
        logger.info("Control listener thread started")
        while self.running:
            try:
                client_socket, client_address = self.control_socket.accept()
                logger.info(f"Control connection from {client_address}")
                self.connected = True
                client_socket.settimeout(0.5)
                while self.running and self.connected:
                    try:
                        data = client_socket.recv(1024)
                        if not data:
                            logger.info("Client disconnected")
                            self.connected = False
                            break
                        self._process_control_data(data, client_socket)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.error(f"Error receiving control data: {e}")
                        self.connected = False
                        break
                try:
                    client_socket.close()
                except:
                    pass
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Control listener error: {e}")
                time.sleep(1)
    
    def _process_control_data(self, data, client_socket):
        try:
            command_data = json.loads(data.decode('utf-8'))
            if self.control_callback:
                self.control_callback(command_data)
                self.last_heartbeat = time.time()
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            logger.error(f"Error processing control data: {e}")

    def _send_data(self, data):
        try:
            if self.connected and hasattr(self, 'client_socket') and self.client_socket:
                self.client_socket.send(data)
        except Exception as e:
            logger.error(f"Error sending data: {e}")
            self.connected = False

    def set_control_callback(self, callback) -> None:
        self.control_callback = callback
    
    def send_telemetry(self, telemetry_data: dict) -> bool:
        logger.debug(f"Would send telemetry: {telemetry_data}")
        return True
    
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
