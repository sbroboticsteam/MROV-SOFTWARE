from smbus2 import SMBus
from time import sleep
import socket
import json
import time
import threading
from enum import Enum
import logging
import random
from typing import Dict, List, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

# PCA9685 constants
PCA9685_ADDRESS = 0x40
MODE1 = 0x00
PRESCALE = 0xFE
LED0_ON_L = 0x06

# --------------------------- PCA9685 and Channel Classes ---------------------------
class PCA9685:
    """Hardware driver for PCA9685 PWM controller."""
    def __init__(self, bus_number=7, address=PCA9685_ADDRESS):
        self.bus = SMBus(bus_number)
        self.address = address
        self.channels = [PCA9685Channel(self, i) for i in range(16)]
        self.reset()
        
    def reset(self):
        self.bus.write_byte_data(self.address, MODE1, 0x00)
        sleep(0.01)

    @property
    def frequency(self):
        return self._frequency

    @frequency.setter
    def frequency(self, freq_hz):
        self._frequency = freq_hz
        prescale_val = int(25000000.0 / (4096 * freq_hz)) - 1

        mode1 = self.bus.read_byte_data(self.address, MODE1)
        # Enter sleep mode
        self.bus.write_byte_data(self.address, MODE1, (mode1 & 0x7F) | 0x10)
        sleep(0.001)
        self.bus.write_byte_data(self.address, PRESCALE, prescale_val)
        sleep(0.001)
        # Exit sleep mode and restart
        self.bus.write_byte_data(self.address, MODE1, mode1)
        sleep(0.005)
        self.bus.write_byte_data(self.address, MODE1, mode1 | 0x80)
        sleep(0.001)

    def deinit(self):
        try:
            self.bus.close()
        except Exception:
            pass

class PCA9685Channel:
    """Individual channel on the PCA9685 PWM controller."""
    def __init__(self, pca, channel):
        self.pca = pca
        self.channel = channel
        self._duty_cycle = 0

    @property
    def duty_cycle(self):
        return self._duty_cycle

    @duty_cycle.setter
    def duty_cycle(self, value):
        self._duty_cycle = value
        on_value = 0
        off_value = value & 0xFFFF
        base_reg = LED0_ON_L + (4 * self.channel)

        # Write registers with a small delay between writes
        self.pca.bus.write_byte_data(self.pca.address, base_reg, on_value & 0xFF)
        sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 1, (on_value >> 8) & 0xFF)
        sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 2, off_value & 0xFF)
        sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 3, (off_value >> 8) & 0xFF)
        sleep(0.001)

# --------------------------- Thruster Class ---------------------------
class Thruster:
    """Electronic Speed Controller (ESC) for thrusters."""
    def __init__(self, channel: int, pca: PCA9685, name: str = "thruster"):
        self.channel = channel
        self.pca = pca
        self.name = name
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1300  # Reverse max pulse
        self.MAX_PULSE = 1700  # Forward max pulse
        self.FORWARD_MIN = 1525  # Minimum pulse to start forward motion
        self.REVERSE_MAX = 1475  # Maximum pulse to start reverse motion
        self.current_pulse = self.STOP_PULSE
        self.current_speed = 0.0  # Speed in range -1.0 to 1.0
        
        # For logging activity
        self.last_speed_change = time.time()
        self.total_active_time = 0.0
        self.direction_changes = 0
        logger.debug(f"Created thruster '{self.name}' on channel {self.channel}")

    def initialize(self) -> None:
        """Initialize ESC with neutral signal."""
        self._set_pulse_width(self.STOP_PULSE)
        sleep(2)
        logger.info(f"Thruster {self.name} on channel {self.channel} initialized")

    def set_speed(self, speed: float) -> None:
        """
        Set thruster speed (-1.0 for full reverse, +1.0 for full forward; 0.0 stops).
        """
        speed = max(-1.0, min(1.0, speed))
        
        if speed > 0:
            pulse_width = self.FORWARD_MIN + (speed * (self.MAX_PULSE - self.FORWARD_MIN))
        elif speed < 0:
            pulse_width = self.REVERSE_MAX - (abs(speed) * (self.REVERSE_MAX - self.MIN_PULSE))
        else:
            pulse_width = self.STOP_PULSE
            
        # Log direction change if applicable
        if (self.current_speed > 0 and speed < 0) or (self.current_speed < 0 and speed > 0):
            self.direction_changes += 1
            logger.debug(f"Thruster {self.name}: Direction change #{self.direction_changes}")
            
        # Update only when speed has changed
        if speed != self.current_speed:
            now = time.time()
            if self.current_speed != 0:
                active_time = now - self.last_speed_change
                self.total_active_time += active_time
            logger.info(f"Thruster {self.name}: {self.current_speed:.2f} -> {speed:.2f} (pulse: {int(pulse_width)})")
            self.current_speed = speed
            self.last_speed_change = now
            self._set_pulse_width(int(pulse_width))
        
    def _set_pulse_width(self, pulse_width: int) -> None:
        """Set ESC pulse width."""
        offset = 9
        pulse_width += offset
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        self.current_pulse = pulse_width
        sleep(0.001)

    def stop(self) -> None:
        """Stop the thruster."""
        prev_speed = self.current_speed
        self.set_speed(0.0)
        logger.info(f"Thruster {self.name} stopped (was: {prev_speed:.2f})")

    def get_stats(self) -> Dict:
        """Return statistics for this thruster."""
        return {
            "name": self.name,
            "channel": self.channel,
            "current_speed": self.current_speed,
            "current_pulse": self.current_pulse,
            "total_active_time": self.total_active_time,
            "direction_changes": self.direction_changes
        }

# --------------------------- Ethernet Manager Class ---------------------------
class EthernetManager:
    """Manages network communications for the ROV."""
    
    def __init__(self, control_ip: str = '192.168.1.237', control_port: int = 4891):
        self.control_ip = control_ip
        self.control_port = control_port
        self.control_socket = None
        self.connected = False
        self.control_thread = None
        self.running = False
        self.control_callback = None
        self.last_heartbeat = 0
        logger.info(f"EthernetManager initialized with IP: {control_ip}:{control_port}")
        
    def start_control_server(self) -> bool:
        """Start the control server to receive commands."""
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.control_socket.bind((self.control_ip, self.control_port))
            self.control_socket.listen(1)
            self.control_socket.settimeout(1.0)  # 1-second accept timeout
            
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
                logger.info(f"Received control connection from {client_address}")
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
                        logger.error(f"Error in receiving control data: {e}")
                        self.connected = False
                        break
                        
                try:
                    client_socket.close()
                except Exception:
                    pass
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Control listener error: {e}")
                time.sleep(1)
                
    def _process_control_data(self, data: bytes, client_socket: socket.socket) -> None:
        try:
            self.last_heartbeat = time.time()
            raw_data = data.decode('utf-8')
            logger.debug(f"Received control data: {raw_data}")
            json_str = raw_data.replace("'", '"')
            control_data = json.loads(json_str)
            if self.control_callback:
                self.control_callback(control_data)
            client_socket.send("ACK".encode('utf-8'))
        except Exception as e:
            logger.error(f"Error processing control data: {e}")
    
    def set_control_callback(self, callback) -> None:
        self.control_callback = callback
    
    def send_telemetry(self, telemetry_data: Dict) -> bool:
        logger.debug(f"Sending telemetry: {telemetry_data}")
        # Here you might implement actual telemetry sending
        return True
    
    def shutdown(self) -> None:
        logger.info("Shutting down EthernetManager")
        self.running = False
        if self.control_socket:
            try:
                self.control_socket.close()
            except Exception:
                pass
        if self.control_thread and self.control_thread.is_alive():
            self.control_thread.join(timeout=1.0)
        logger.info("EthernetManager shutdown complete")

# --------------------------- Minimal ROV Class for Thruster Testing ---------------------------
class ROV:
    """Minimal ROV system for testing thruster functionality and Ethernet communication."""
    
    def __init__(self):
        logger.info("Initializing minimal ROV for thruster testing...")
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50
        
        # Create thruster objects using a predefined channel map
        self.thruster_channels = [0, 7, 2, 5, 1, 4, 6, 3]
        self.thruster_names = [
            "FrontLeft", "FrontLeftUp", "BackLeft", "BackLeftUp",
            "FrontRightUp", "BackRight", "BackRightUp", "FrontRight"
        ]
        self.thrusters = []
        for i, channel in enumerate(self.thruster_channels):
            name = self.thruster_names[i] if i < len(self.thruster_names) else f"Thruster{i}"
            self.thrusters.append(Thruster(channel, self.pca, name=name))
        
        # Initialize Ethernet Manager for network communication
        self.ethernet = EthernetManager(control_ip='192.168.1.237', control_port=4891)
        self.ethernet.set_control_callback(self._process_control_data)
        
        self.running = False
        logger.info("Minimal ROV initialization complete")
    
    def start(self) -> None:
        """Start the ROV system for thruster testing."""
        logger.info("Starting minimal ROV system...")
        for thruster in self.thrusters:
            thruster.initialize()
        self.ethernet.start_control_server()
        self.running = True
        self._main_loop()
    
    def _main_loop(self) -> None:
        """Main loop for thruster testing."""
        logger.info("Entering main loop. Waiting for control commands to set thruster speeds...")
        while self.running:
            try:
                time.sleep(0.1)  # Small delay for loop iteration
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(0.5)
    
    def _process_control_data(self, control_data: Dict) -> None:
        """Process control data to update thruster speeds."""
        try:
            if 'motor_values' in control_data:
                motor_values = control_data['motor_values']
                if isinstance(motor_values, list) and len(motor_values) == len(self.thrusters):
                    for i, thruster in enumerate(self.thrusters):
                        thruster.set_speed(motor_values[i])
                    logger.info("Thruster speeds updated via control data")
        except Exception as e:
            logger.error(f"Error processing control data: {e}")
    
    def shutdown(self) -> None:
        """Shutdown the ROV system."""
        logger.info("Shutting down minimal ROV system...")
        self.running = False
        for thruster in self.thrusters:
            thruster.stop()
        self.ethernet.shutdown()
        self.pca.deinit()
        logger.info("Minimal ROV system shutdown complete")

# --------------------------- Main Entry Point ---------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description='Minimal ROV Thruster Test')
    parser.add_argument('--log-level', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')
    args = parser.parse_args()
    logging.getLogger().setLevel(args.log_level)
    
    rov = ROV()
    try:
        rov.start()
    except KeyboardInterrupt:
        logger.info("Minimal ROV interrupted by user")
        rov.shutdown()
    except Exception as e:
        logger.error(f"Error in Minimal ROV system: {e}")
        rov.shutdown()

if __name__ == '__main__':
    main()
