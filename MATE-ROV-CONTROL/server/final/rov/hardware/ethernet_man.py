import socket
import threading
import time
import json
import logging
import subprocess
from typing import Dict, Optional,List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

# --------------------------- Ethernet Manager Class ---------------------------
class EthernetManager:
    """Manages all network communications for the ROV using UDP"""
    def __init__(self, control_ip: str = '192.168.50.41', control_port: int = 4891, camera_port: int = 8000,telemetry_ip: str = '192.168.50.142', telemetry_port: int = 8001):
        self.control_ip = control_ip
        self.control_port = control_port
        self.camera_port = camera_port  # Add camera port
        self.control_socket = None
        self.camera_socket = None  # Add camera socket
        self.connected = False
        self.control_thread = None
        self.camera_thread = None  # Add camera thread
        self.running = False
        self.control_callback = None
        self.last_heartbeat = 0
        self.client_address = None  # Store the most recent client's address
        self.stream_processes = []  # Add stream processes list
        logger.info(f"Ethernet manager initialized with UDP control IP: {control_ip}:{control_port}, Camera port: {camera_port}")
                # Add these new fields for dedicated telemetry
        self.telemetry_ip = telemetry_ip
        self.telemetry_port = telemetry_port
        self.telemetry_running = False
        self.telemetry_thread = None
        self.telemetry_interval = 0.5  # Send telemetry every 5 seconds
        self.latest_telemetry = {}
        
        # Start the dedicated telemetry thread
        self.start_telemetry_sender()
    
    # Add this new method
    def start_telemetry_sender(self) -> bool:
        """Start a dedicated thread to send telemetry data periodically"""
        if self.telemetry_running:
            logger.warning("Telemetry sender already running")
            return False
            
        try:
            # Create a socket for sending telemetry
            self.telemetry_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.telemetry_running = True
            self.telemetry_thread = threading.Thread(target=self._telemetry_sender)
            self.telemetry_thread.daemon = True
            self.telemetry_thread.start()
            logger.info(f"Started telemetry sender thread to {self.telemetry_ip}:{self.telemetry_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start telemetry sender: {e}")
            return False
    
    # Add this new method
    def _telemetry_sender(self) -> None:
        """Thread function to periodically send telemetry data"""
        logger.info(f"Telemetry sender thread running, sending to {self.telemetry_ip}:{self.telemetry_port} every {self.telemetry_interval}s")
        
        while self.telemetry_running:
            try:
                # If we have telemetry data, send it
                if self.latest_telemetry:
                    # Add timestamp and extra diagnostic info
                    telemetry_data = self.latest_telemetry.copy()
                    telemetry_data["timestamp"] = time.time()
                    telemetry_data["rov_status"] = {
                        "connected": self.connected,
                        "client_ip": str(self.client_address[0]) if self.client_address else "None"
                    }
                    
                    # Encode and send
                    json_data = json.dumps(telemetry_data).encode('utf-8')
                    self.telemetry_socket.sendto(json_data, (self.telemetry_ip, self.telemetry_port))
                    logger.debug(f"Sent {len(json_data)} bytes of telemetry to {self.telemetry_ip}:{self.telemetry_port}")
                else:
                    logger.debug("No telemetry data available to send")
                    
                    # Send a minimal heartbeat packet even if no other telemetry
                    heartbeat = {
                        "heartbeat": True,
                        "timestamp": time.time(),
                        "rov_status": {
                            "connected": self.connected,
                            "client_ip": str(self.client_address[0]) if self.client_address else "None"
                        }
                    }
                    json_data = json.dumps(heartbeat).encode('utf-8')
                    self.telemetry_socket.sendto(json_data, (self.telemetry_ip, self.telemetry_port))
            except Exception as e:
                logger.error(f"Error in telemetry sender: {e}")
            
            # Sleep for the specified interval
            time.sleep(self.telemetry_interval)
            
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

            # Start camera server on TCP (for reliable connection)
            self.camera_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.camera_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.camera_socket.bind(('0.0.0.0', self.camera_port))
            self.camera_socket.settimeout(1.0)
            self.camera_socket.listen(5)
            self.camera_thread = threading.Thread(target=self._camera_listener, daemon=True)
            self.camera_thread.start()
            logger.info(f"Camera server started on port {self.camera_port}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to start servers: {e}")
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

    def _camera_listener(self) -> None:
        """Listens for camera stream requests on TCP socket"""
        logger.info(f"Camera server listening on port {self.camera_port}")
        
        while self.running:
            try:
                client_socket, addr = self.camera_socket.accept()
                logger.info(f"Camera stream request from {addr}")
                
                # Handle this connection in a new thread
                camera_client_thread = threading.Thread(
                    target=self._handle_camera_client,
                    args=(client_socket, addr),
                    daemon=True
                )
                camera_client_thread.start()
                
            except socket.timeout:
                # Just a timeout, continue
                pass
            except Exception as e:
                if self.running:
                    logger.error(f"Camera server error: {e}")
                time.sleep(0.5)
    
    def _handle_camera_client(self, client_socket, addr):
        """Handle a camera stream request from a client"""
        try:
            # Set a timeout for receiving data
            client_socket.settimeout(5.0)
            
            # Receive the stream configuration
            data = client_socket.recv(1024).decode('utf-8')
            if data:
                try:
                    config = json.loads(data)
                    logger.info(f"Received camera stream config: {config}")
                    
                    # Stop any existing streams
                    self.stop_camera_streams()
                    
                    # Extract configuration
                    client_ip = config.get('client_ip')
                    zed_port = config.get('zed_port', 5000)
                    usb0_port = config.get('usb0_port', 5004)
                    usb2_port = config.get('usb2_port', 5005)
                    camera_360_port = config.get('camera_360_port', 5001)
                    
                    # Start the requested streams
                    success = self.start_camera_streams(client_ip, zed_port, usb0_port, usb2_port, camera_360_port)
                    
                    # Send a response
                    if success:
                        response = {"status": "streams_started"}
                    else:
                        response = {"status": "error", "message": "Failed to start streams"}
                        
                    client_socket.send(json.dumps(response).encode('utf-8'))
                    
                except json.JSONDecodeError:
                    logger.error("Invalid JSON in camera request")
                    client_socket.send(json.dumps({
                        "status": "error", 
                        "message": "Invalid JSON"
                    }).encode('utf-8'))
        except Exception as e:
            logger.error(f"Error handling camera client: {e}")
        finally:
            client_socket.close()
    
    def start_camera_streams(self, client_ip, zed_port, usb0_port, usb2_port, camera_360_port) -> bool:
        """Start the camera streams pointing to the client"""
        try:
            logger.info(f"Starting camera streams to {client_ip}")
            
            commands = [
                [
                    "gst-launch-1.0", "zedsrc", "camera-resolution=3", "camera-fps=30", "stream-type=0", "!",
                    "videoconvert", "!", "x264enc", "byte-stream=true", "tune=zerolatency",
                    "speed-preset=superfast", "bitrate=10000", "!", "h264parse", "!", "rtph264pay",
                    "config-interval=-1", "pt=96", "!", "udpsink",
                    f"host={client_ip}", f"port={zed_port}", "sync=false", "async=false"
                ],
                [
                    "gst-launch-1.0", "-v", "v4l2src", "device=/dev/video4", "!",
                    "image/jpeg,width=640,height=480,framerate=30/1", "!", "jpegparse", "!",
                    "rtpjpegpay", "pt=26", "!", "udpsink",
                    f"host={client_ip}", f"port={usb0_port}", "sync=false", "async=false"
                ],
                [
                    "gst-launch-1.0", "-v", "v4l2src", "device=/dev/video2", "!",
                    "image/jpeg,width=640,height=480,framerate=30/1", "!", "jpegparse", "!",
                    "rtpjpegpay", "pt=26", "!", "udpsink",
                    f"host={client_ip}", f"port={usb2_port}", "sync=false", "async=false"
                ],
                [
                    "gst-launch-1.0", "v4l2src", "device=/dev/video0", "!",
                    "video/x-h264,width=1920,height=960,framerate=30/1", "!",
                    "h264parse", "!", "avdec_h264", "!", "videoconvert", "!",
                    "x264enc", "bitrate=4000", "speed-preset=ultrafast", "tune=zerolatency", "!",
                    "h264parse", "!", "rtph264pay", "config-interval=1", "pt=96", "!",
                    "udpsink", f"host={client_ip}", f"port={camera_360_port}", "sync=false", "async=false"
                ]
            ]
            
            for cmd in commands:
                logger.info(f"Launching: {' '.join(cmd)}")
                try:
                    process = subprocess.Popen(cmd)
                    self.stream_processes.append(process)
                except Exception as e:
                    logger.error(f"Failed to start stream process: {e}")
            
            return len(self.stream_processes) > 0
            
        except Exception as e:
            logger.error(f"Error starting camera streams: {e}")
            return False
    
    def stop_camera_streams(self):
        """Stop all running camera stream processes"""
        if self.stream_processes:
            logger.info("Stopping camera streams")
            for process in self.stream_processes:
                try:
                    process.terminate()
                except:
                    pass
            self.stream_processes = []
    
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
    
    # Modify the existing send_telemetry method
    def send_telemetry(self, telemetry_data: dict) -> bool:
        """Send telemetry data to the connected client and update latest telemetry"""
        try:
            # Store the latest telemetry data for the dedicated sender
            self.latest_telemetry.update(telemetry_data)
            
            # Also send immediately to the connected control client if available
            if self.connected and self.client_address:
                json_data = json.dumps(telemetry_data).encode('utf-8')
                self.control_socket.sendto(json_data, self.client_address)
                return True
            return False
        except Exception as e:
            logger.error(f"Error sending telemetry: {e}")
            return False
    # Don't forget to add cleanup to the existing methods
    def close(self):
        """Close all network connections"""
        self.telemetry_running = False
        self.running = False  # Add this line to signal threads to stop
        
        # Stop all stream processes first
        self.stop_camera_streams()
        
        if hasattr(self, 'telemetry_socket'):
            try:
                self.telemetry_socket.close()
            except:
                pass
                
        if hasattr(self, 'control_socket'):
            try:
                self.control_socket.close()
            except:
                pass
                
        if hasattr(self, 'camera_socket'):
            try:
                self.camera_socket.close()
            except:
                pass
    def shutdown(self) -> None:
        """Safely shutdown the ethernet manager."""
        self.running = False
        # Stop camera streams
        self.stop_camera_streams()
        
        # Close camera socket
        if hasattr(self, 'camera_socket') and self.camera_socket:
            try:
                self.camera_socket.close()
            except:
                pass
        
        # Join camera thread
        if hasattr(self, 'camera_thread') and self.camera_thread:
            self.camera_thread.join(timeout=1.0)

        if hasattr(self, 'control_thread') and self.control_thread:
            self.control_thread.join(timeout=1.0)
        if hasattr(self, 'control_socket') and self.control_socket:
            try:
                self.control_socket.close()
            except:
                pass
        logger.info("Ethernet manager shutdown complete")

# If name is main
if __name__ == "__main__":
    # Debug the camera functionality independently
    try:
        # Create EthernetManager with default settings
        ethernet_manager = EthernetManager()
        
        print(f"Starting camera server for debugging on port {ethernet_manager.camera_port}")
        print("Press Ctrl+C to exit")
        
        # Start the servers
        if ethernet_manager.start_control_server():
            print("Camera server started successfully")
            
            # Just keep the main thread alive
            while True:
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error during debugging: {e}")
    finally:
        # Make sure to clean up resources
        if 'ethernet_manager' in locals():
            ethernet_manager.shutdown()
            print("Shutdown complete")