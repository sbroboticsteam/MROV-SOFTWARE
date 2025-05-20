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
import numpy as np
import sys
import argparse
import os

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

# --------------------------- Controller Mapper Class ---------------------------
class ControllerMapper:
    """Maps controller inputs based on user-defined configurations."""
    
    # Default mapping (no remapping)
    DEFAULT_MAPPING = {
        # Analog inputs
        'left_stick_x': 'left_stick_x',
        'left_stick_y': 'left_stick_y',
        'right_stick_x': 'right_stick_x',
        'right_stick_y': 'right_stick_y',
        'left_trigger': 'left_trigger',
        'right_trigger': 'right_trigger',
        
        # Digital inputs
        'a': 'a',
        'b': 'b',
        'x': 'x',
        'y': 'y',
        'lb': 'lb',
        'rb': 'rb',
        'back': 'back',
        'start': 'start',
        
        # D-pad 
        'dpad_x': 'dpad_x',
        'dpad_y': 'dpad_y'
    }
    
    def __init__(self):
        self.mapping = self.DEFAULT_MAPPING.copy()
        self.config_file = "controller_mapping.json"
        self.load_mapping()
        
    def load_mapping(self):
        """Load controller mapping from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    saved_mapping = json.load(f)
                    # Validate the mapping before applying
                    if self._validate_mapping(saved_mapping):
                        self.mapping = saved_mapping
                        logger.info("Controller mapping loaded successfully")
                    else:
                        logger.warning("Invalid mapping in config file, using default mapping")
                        self.mapping = self.DEFAULT_MAPPING.copy()
            else:
                logger.info("No controller mapping found, using default mapping")
        except Exception as e:
            logger.error(f"Error loading controller mapping: {e}")
            self.mapping = self.DEFAULT_MAPPING.copy()
    
    def save_mapping(self):
        """Save the current controller mapping to a file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.mapping, f, indent=2)
            logger.info("Controller mapping saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving controller mapping: {e}")
            return False
    
    def _validate_mapping(self, mapping):
        """Validate that a mapping contains all necessary keys and valid targets"""
        valid_sources = set(self.DEFAULT_MAPPING.keys())
        valid_targets = set(self.DEFAULT_MAPPING.keys())
        
        # Check if all required sources are in the mapping
        if not all(source in mapping for source in valid_sources):
            return False
            
        # Check if all targets are valid
        if not all(target in valid_targets for target in mapping.values()):
            return False
            
        return True
    
    def set_mapping(self, source, target):
        """Set a new mapping from source to target"""
        if source in self.mapping and target in self.DEFAULT_MAPPING.keys():
            self.mapping[source] = target
            logger.info(f"Remapped '{source}' to '{target}'")
            return True
        else:
            logger.error(f"Invalid mapping: {source} -> {target}")
            return False
    
    def reset_mapping(self):
        """Reset mapping to default"""
        self.mapping = self.DEFAULT_MAPPING.copy()
        logger.info("Controller mapping reset to default")
        return True
    
    def apply_mapping(self, controller_data):
        """Apply the current mapping to controller data"""
        if not controller_data:
            return {}
            
        mapped_data = {}
        
        # Process each input according to the mapping
        for source, target in self.mapping.items():
            if source in controller_data:
                mapped_data[target] = controller_data[source]
        
        return mapped_data
    
    def get_current_mapping(self):
        """Return the current mapping"""
        return self.mapping.copy()


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
            # logger.info(f"Thruster {self.name}: {self.current_speed:.2f} -> {speed:.2f} (pulse: {int(pulse_width)})")
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

try:
    from bno055 import BNO055, BNO055_ADDRESS_A
    BNO055_AVAILABLE = True
    logger.info("BNO055 module successfully imported")
except ImportError:
    BNO055_AVAILABLE = False
    logger.warning("Could not import BNO055 class. IMU functionality will be limited.")
    BNO055 = None

class IMUSensor:
    """Interface to the BNO055 IMU sensor for orientation sensing."""
    def __init__(self, bus_number=7, address=BNO055_ADDRESS_A if BNO055_AVAILABLE else None):
        self.bno = None
        self.available = False
        self.last_read_time = 0
        self.read_interval = 0.02  # 50Hz max reading rate
        self.last_heading = 0
        self.last_roll = 0
        self.last_pitch = 0
        self.calibration_status = (0, 0, 0, 0)  # sys, gyro, accel, mag
        
        if BNO055_AVAILABLE and address:
            try:
                logger.info("Initializing BNO055 sensor...")
                self.bno = BNO055(bus_number=bus_number, address=address)
                if not self.bno.begin():
                    logger.error("Failed to initialize BNO055!")
                    self.available = False
                else:
                    logger.info("BNO055 Initialized Successfully.")
                    # Check initial calibration
                    time.sleep(1)  # Wait a bit after init
                    self.calibration_status = self.bno.get_calibration()
                    logger.info(f"Initial Calibration: Sys={self.calibration_status[0]}, "
                                f"Gyro={self.calibration_status[1]}, "
                                f"Accel={self.calibration_status[2]}, "
                                f"Mag={self.calibration_status[3]}")
                    self.available = True
                    
                    # Initial read
                    self._read_orientation()
            except Exception as e:
                logger.error(f"Exception during BNO055 initialization: {e}")
                self.available = False
        else:
            logger.warning("BNO055 not available. Orientation sensing disabled.")
            self.available = False
    
    def _read_orientation(self):
        """Read the current orientation from the BNO055 sensor."""
        if not self.available or not self.bno:
            return self.last_heading, self.last_roll, self.last_pitch
            
        current_time = time.time()
        # Throttle reads to avoid overwhelming the I2C bus
        if current_time - self.last_read_time < self.read_interval:
            return self.last_heading, self.last_roll, self.last_pitch
            
        try:
            # Get Euler angles in degrees
            heading, roll, pitch = self.bno.get_euler()
            
            # Apply offset correction: subtract 2.69 from roll value
            roll += 2.69
            pitch -= 8.44
            
            # Update last read values
            self.last_heading = heading
            self.last_roll = roll
            self.last_pitch = pitch
            self.last_read_time = current_time
            
            # Periodically update calibration status
            if current_time % 5 < 0.1:  # Every ~5 seconds
                self.calibration_status = self.bno.get_calibration()
                
            return heading, roll, pitch
            
        except Exception as e:
            logger.error(f"Error reading orientation: {e}")
            return self.last_heading, self.last_roll, self.last_pitch
    
    def get_orientation(self):
        """Get the current orientation (heading, roll, pitch) in degrees."""
        if self.available:
            return self._read_orientation()
        return 0, 0, 0  # Default values if not available
    
    def get_calibration_status(self):
        """Get current calibration status (sys, gyro, accel, mag)."""
        if self.available:
            try:
                self.calibration_status = self.bno.get_calibration()
            except Exception as e:
                logger.error(f"Error reading calibration status: {e}")
        return self.calibration_status
    
    def is_calibrated(self, min_sys=2, min_gyro=3, min_accel=2, min_mag=2):
        """Check if the sensor is adequately calibrated."""
        if not self.available:
            return False
            
        sys, gyro, accel, mag = self.get_calibration_status()
        return (sys >= min_sys and gyro >= min_gyro and 
                accel >= min_accel and mag >= min_mag)
    
    def close(self):
        """Close connection to the sensor."""
        if self.available and self.bno:
            try:
                self.bno.close()
                logger.info("IMU sensor connection closed")
            except Exception as e:
                logger.error(f"Error closing IMU sensor: {e}")

class ElapsedTime:
    def __init__(self):
        self.reset()

    def reset(self):
        self._start_time = time.time()

    def seconds(self):
        return time.time() - self._start_time
    
class PID_Controller:
    def __init__(self, *args):
        self.runtime = ElapsedTime()
        self.tolerance = 0.0
        self.area = 0.0
        self.kp = 0.0
        self.kd = 0.0
        self.ki = 0.0
        self.a = 0.0

        self.P = 0.0
        self.I = 0.0
        self.D = 0.0

        self.delta_time = 0.0
        self.previous_error = 0.0
        self.previous_target = 0.0
        self.previous_filter_estimate = 0.0
        self.current_filter_estimate = 0.0
        self.error_change = 0.0
        self.error = 0.0
        self.name = "PID"

        # Support constructor overloads
        if len(args) == 1:
            self.kp = args[0]
        elif len(args) == 2:
            self.kp = args[0]
            self.kd = args[1]
        elif len(args) == 3:
            self.kp = args[0]
            self.kd = args[1]
            self.ki = args[2]
        elif len(args) == 4:
            self.kp = args[0]
            self.kd = args[1]
            self.ki = args[2]
            self.a = args[3]
            
    def set_name(self, name):
        """Set a name for this PID controller for identification in logs"""
        self.name = name
        return self

    def PID_Power(self, curr_pos, target_pos):
        self.error = target_pos - curr_pos
        self.error_change = self.error - self.previous_error

        self.P = self.kp * self.error

        self.delta_time = self.runtime.seconds()
        self.runtime.reset()

        self.area += ((self.error + self.previous_error) * self.delta_time) / 2

        if abs(self.error) < self.tolerance:
            self.area = 0.0
        if target_pos != self.previous_target:
            self.area = 0.0

        self.I = self.area * self.ki

        self.current_filter_estimate = ((1 - self.a) * self.error_change +
                                        self.a * self.previous_filter_estimate)

        self.D = self.kd * (self.current_filter_estimate / self.delta_time)
        
         # Log PID components at DEBUG level
        logger.debug(f"PID {self.name}: Target={target_pos:.2f}, Current={curr_pos:.2f}, Error={self.error:.2f}")
        logger.debug(f"PID {self.name}: P={self.P:.4f} (kp={self.kp}), I={self.I:.4f}, D={self.D:.4f}, Output={self.P + self.I + self.D:.4f}")

        self.previous_error = self.error
        self.previous_filter_estimate = self.current_filter_estimate
        self.previous_target = target_pos

        return self.P + self.I + self.D

    def reset(self):
        self.previous_error = 0.0
        self.area = 0.0  # Change from self.integral
        self.runtime.reset()

# --------------------------- Chassis Control Class ---------------------------
class ChassisControl:
    def __init__(self):
        # Initialize target values
        self.x_target = 0
        self.y_target = 0
        self.z_target = 0
        self.yaw_target = 0
        self.pitch_target = 0
        self.roll_target = 0


        # Use named PID controllers for better logging
        self.pidX = PID_Controller(0, 0, 0, 0).set_name("X")
        self.pidY = PID_Controller(0, 0, 0, 0).set_name("Y")
        self.pidZ = PID_Controller(0, 0, 0, 0).set_name("Z")
        self.pidRoll = PID_Controller(0.02, 0, 0, 0).set_name("Roll")
        self.pidPitch = PID_Controller(0.02, 0, 0, 0).set_name ("Pitch")
        self.pidYaw = PID_Controller(0, 0, 0, 0).set_name("Yaw")
        
    def updateTarget(self, imuData, x, y, rx, ry, rT, lT):
        logger.debug(f"BEFORE Target Update - Yaw: {self.yaw_target:.2f}°, Roll: {self.roll_target:.2f}°, Pitch: {self.pitch_target:.2f}°")
        e = sys.float_info.epsilon
        if abs(x) > e :
            self.x_target = imuData[0]
            logger.info(f"*** X target UPDATED to {self.x_target:.2f} ***")
        if abs(y) > e :
            self.y_target = imuData[1]
            logger.info(f"*** Y target UPDATED to {self.y_target:.2f} ***")
        if abs(rx) > e :
            self.yaw_target = imuData[5]
            logger.info(f"*** Yaw target UPDATED to {self.yaw_target:.2f}° (input: {rx:.2f}) ***")
        if abs(ry) >  e :
            self.pitch_target = imuData[4]
            logger.info(f"*** PITCH target UPDATED to {self.pitch_target:.2f}° (input: {ry:.2f}) ***")
        if abs(rT) > e  or abs(lT) > e  :
            self.z_target = imuData[2]
            logger.info(f"*** Z target UPDATED to {self.z_target:.2f} ***")
        
        logger.debug(f"AFTER Target Update - Yaw: {self.yaw_target:.2f}°, Roll: {self.roll_target:.2f}°, Pitch: {self.pitch_target:.2f}°")

    def arcadeDrive6(self, input_vector):
        """
        Advanced arcade drive with 6 degrees of freedom.
        input_vector: [x, y, z, roll, pitch, yaw]
        """
        # Inverse Kinematics for Planar Thrusters (X-Y movement and rotation)
        planar_front_left = -input_vector[1] +input_vector[0] + input_vector[5]
        planar_front_right = -input_vector[1] -input_vector[0] - input_vector[5]
        planar_back_right = input_vector[1] -input_vector[0] + input_vector[5]
        planar_back_left = input_vector[1] +input_vector[0] - input_vector[5]

        # Inverse Kinematics for Vertical Thrusters (Depth and Roll-Pitch Corrections)
        vertical_front_left = -input_vector[2] - input_vector[3] + input_vector[4]
        vertical_front_right = -input_vector[2] + input_vector[3] + input_vector[4]
        vertical_back_right = -input_vector[2] - input_vector[3] - input_vector[4]
        vertical_back_left = -input_vector[2] + input_vector[3] - input_vector[4]

        # Normalize Planar and Vertical Thruster Values
        planar_thrusters = self._normalize_thrusters([-planar_front_left, -planar_front_right, -planar_back_left, -planar_back_right])
        vertical_thrusters = self._normalize_thrusters([-vertical_front_left, -vertical_front_right, -vertical_back_right, -vertical_back_left])

        # Return motor power values for all thrusters
        return planar_thrusters + vertical_thrusters
    
    def _normalize_thrusters(self, thrusters):
        """Normalize thruster values if any exceed limits."""
        max_val = max(abs(t) for t in thrusters)
        if max_val > 1.0:
            thrusters = [t / max_val for t in thrusters]
        return thrusters
    
    def addVectors(self, vec1, vec2):
        """Add two vectors element-wise."""
        return [x + y for x, y in zip(vec1, vec2)]
    
    def controllerInput(self, x, y, rx, ry, rT, lT):
        """Convert raw controller inputs to a 6-axis control vector."""
        vert = rT - lT
        data = [x, y, vert, 0, ry, rx]  # [x, y, z, roll, pitch, yaw]
        return data
    
    def PIDcorrection(self, imuData):
        """
        Calculate PID corrections based on IMU data.
        imuData: [x, y, z, roll, pitch, yaw] from IMU sensor
        """
        # Calculate power adjustments for each axis
        powerX = self.pidX.PID_Power(imuData[0], self.x_target)
        powerY = self.pidY.PID_Power(imuData[1], self.y_target)
        powerZ = self.pidZ.PID_Power(imuData[2], self.z_target)
        
        # For stability, try to keep roll and pitch at 0
        powerRoll = self.pidRoll.PID_Power(imuData[3], self.roll_target)  # Always target level
        powerPitch = -self.pidPitch.PID_Power(imuData[4], self.pitch_target) 
        
        # Yaw needs to match the target heading
        powerYaw = self.pidYaw.PID_Power(imuData[5], self.yaw_target)
        
        power = [powerX, powerY, powerZ, powerRoll, powerPitch, powerYaw]
        return power

    #fix later
    def rotateVectors(self, power):
        """
        Rotate power vectors according to current orientation.
        This converts body-relative commands to world-relative commands.
        """
        roll_rad = np.radians(power[3])
        pitch_rad = np.radians(power[4])
        yaw_rad = np.radians(power[5])
        
        x_rotated = (power[0] * (np.cos(yaw_rad) * np.cos(pitch_rad)) +
                    power[1] * (np.cos(yaw_rad) * np.sin(pitch_rad) * np.sin(roll_rad) - np.sin(yaw_rad) * np.cos(roll_rad)) +
                    power[2] * (np.cos(yaw_rad) * np.sin(pitch_rad) * np.cos(roll_rad) + np.sin(yaw_rad) * np.sin(roll_rad)))

        y_rotated = (power[0] * (np.sin(yaw_rad) * np.cos(pitch_rad)) +
                    power[1] * (np.sin(yaw_rad) * np.sin(pitch_rad) * np.sin(roll_rad) + np.cos(yaw_rad) * np.cos(roll_rad)) +
                    power[2] * (np.sin(yaw_rad) * np.sin(pitch_rad) * np.cos(roll_rad) - np.cos(yaw_rad) * np.sin(roll_rad)))

        z_rotated = (-power[0] * np.sin(pitch_rad) +
                    power[1] * (np.cos(pitch_rad) * np.sin(roll_rad)) +
                    power[2] * (np.cos(pitch_rad) * np.cos(roll_rad)))
        
        return [x_rotated, y_rotated, z_rotated, power[3], power[4], power[5]]

# --------------------------- Servo Class ---------------------------
class Servo:
    def __init__(self, channel, pca, min_pulse=900, max_pulse=2100, name="unnamed"):
        self.channel = channel
        self.pca = pca
        self.min_pulse = min_pulse
        self.max_pulse = max_pulse
        self.current_pulse = 1500  # Neutral position
        self.name = name
        
    def set_angle(self, angle):
        """Set servo position using angle (0-180°)"""
        # Ensure angle is within bounds
        angle = max(0, min(180, angle))
        # Convert angle to value (-1 to 1)
        value = (angle / 90.0) - 1.0
        # Map value to pulse width
        pulse_width = self._map_value_to_pulse(value)
        self._set_pulse_width(pulse_width)
        
    def _map_value_to_pulse(self, value):
        """Map a value from -1,1 to min_pulse,max_pulse"""
        value = max(-1.0, min(1.0, value))  # Ensure value is in range
        return self.min_pulse + (value + 1) * (self.max_pulse - self.min_pulse) / 2
        
    def _set_pulse_width(self, pulse_width):
        """Set the servo pulse width directly"""
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        logger.debug(f"{self.name} (Channel {self.channel}): {pulse_width} µs")
        self.current_pulse = pulse_width
        time.sleep(0.001)  # Small delay to help register changes

# --------------------------- Arm State Enum ---------------------------
class ArmState(Enum):
    """State enum for arm positions"""
    STOWED = 0      # Arm in storage/travel position (X button)
    FULLY_OUT = 1   # Arm fully extended straight out (Y button)
    FULLY_DOWN = 2  # Arm fully down (Right Bumper)
    OUT_DOWN = 3    # Arm out with elbow down (Left Bumper)

# --------------------------- Arm Control Class ---------------------------
class Arm:
    """Main class that controls all arm servos"""
    
    # Preset positions based on actual calibrated pulse values
    # Converted from pulse values to angles using reverse calculation
    POSITIONS = {
        ArmState.STOWED: {
            "claw": 180,     # Closed position
            "wrist": 0,      # Horizontal rotation
            "elbow": 100,    # Final stowed position for elbow
            "shoulder": 0   # Final stowed position for shoulder
        },
        ArmState.FULLY_OUT: {
            "claw": 0,       # Open position
            "wrist": 90,     # Vertical
            "elbow": 100,    # Down position (~1940μs)
            "shoulder": 145  # Extended out (~1681μs)
        },
        ArmState.FULLY_DOWN: {
            "claw": 0,       # Open position
            "wrist": 90,     # Vertical
            "elbow": 160,    # Down position (~1940μs)
            "shoulder": 45  # Down position (~1186μs)
        },
        ArmState.OUT_DOWN: {
            "claw": 0,       # Open position
            "wrist": 90,     # Vertical
            "elbow": 160,    # Down position (~1940μs)
            "shoulder": 145  # Extended out (~1681μs)
        }
    }
    
    def __init__(self, pca):
        """Initialize the arm with all servos"""
        self.pca = pca
        self.current_state = None
        
        # Create servo objects with correct channel assignments and names
        self.servos = {
            "claw": Servo(3, pca, min_pulse=900, max_pulse=2100, name="Claw"),
            "wrist": Servo(2, pca, min_pulse=900, max_pulse=2000, name="Wrist"),
            "elbow": Servo(0, pca, min_pulse=900, max_pulse=2100, name="Elbow"),
            "shoulder": Servo(1, pca, min_pulse=900, max_pulse=2100, name="Shoulder")
        }
        
        # Store the current wrist angle for rotation control
        self.current_wrist_angle = 90  # Start at neutral/vertical
        self.current_claw_angle = 180 # def closed
        
        # Initialize to stowed position
        self.set_state(ArmState.FULLY_OUT)
        
    def set_state(self, state):
        """Set the arm to a predefined state"""
        if state not in ArmState:
            logger.error(f"Invalid state: {state}")
            return False
            
        logger.info(f"Setting arm to {state.name} position...")
        
        # Special handling for stowed position
        if state == ArmState.STOWED:
            self._set_stowed_position()
        else:
            # Get the preset positions for this state
            positions = self.POSITIONS[state]
            
            # Set each servo to its position with a small delay between each
            for servo_name, angle in positions.items():
                # Skip wrist adjustment if already at target angle
                if servo_name == "wrist" and abs(self.current_wrist_angle - angle) < 5:
                    continue
                    
                self.servos[servo_name].set_angle(angle)
                
                # Update current wrist angle if we're adjusting it
                if servo_name == "wrist":
                    self.current_wrist_angle = angle
                    
                time.sleep(0.1)  # Small delay between servo movements
            
        self.current_state = state
        logger.info(f"Arm now in {state.name} position")
        return True
    
    def _set_stowed_position(self):
        """Special method to handle the stowing process in correct sequence"""
        logger.info("Beginning arm stow sequence...")

        if(self.current_state == ArmState.STOWED): 
            logger.info("Arm already in stowed position, no action taken")
            return
        
        # First set claw and wrist to their stowed positions
        logger.info("Step 1: Setting claw and wrist positions")
        self.servos["claw"].set_angle(self.POSITIONS[ArmState.STOWED]["claw"])
        self.servos["wrist"].set_angle(self.POSITIONS[ArmState.STOWED]["wrist"])
        self.current_wrist_angle = self.POSITIONS[ArmState.STOWED]["wrist"]
        time.sleep(0.3)  # Wait for these servos to move
        
        # Step 2: Move elbow down first for safety
        logger.info("Step 2: Moving elbow down")
        self.servos["elbow"].set_angle(160)  # Move elbow down (~1980μs)
        time.sleep(0.5)  # Wait for elbow to complete movement
        
        # Step 3: Retract shoulder completely
        logger.info("Step 3: Retracting shoulder")
        self.servos["shoulder"].set_angle(0)  # Move shoulder in (~950μs)
        time.sleep(0.8)  # Wait longer for shoulder to complete movement
        
        # Step 4: Set final elbow position
        logger.info("Step 4: Setting final elbow position")
        self.servos["elbow"].set_angle(100)  # Move elbow to final position
        time.sleep(0.5)  # Wait for elbow to complete movement
        
        
        logger.info("Arm stow sequence completed successfully")

    # def open_claw(self):
    #     """Open the claw"""
    #     self.servos["claw"].set_angle(0)  # 0° = open
    #     print("Claw opened")
        
    # def close_claw(self):
    #     """Close the claw"""
    #     self.servos["claw"].set_angle(180)  # 180° = closed
    #     print("Claw closed")

    def adjust_claw(self, direction, step=5):
        new_angle = self.current_claw_angle + (direction * step)
        new_angle = max(0, min(180, new_angle))  # Ensure within bounds
        
        if new_angle != self.current_claw_angle:
            self.servos["claw"].set_angle(new_angle)
            self.current_claw_angle = new_angle
            print(f"claw rotated to {new_angle}°")
        
    def adjust_wrist(self, direction, step=5):
        """
        Adjust wrist rotation incrementally
        direction: -1 for left, 1 for right
        step: angle change in degrees
        """
        # Calculate new angle based on direction
        new_angle = self.current_wrist_angle + (direction * step)
        new_angle = max(0, min(180, new_angle))  # Ensure within bounds
        
        if new_angle != self.current_wrist_angle:
            self.servos["wrist"].set_angle(new_angle)
            self.current_wrist_angle = new_angle
            print(f"Wrist rotated to {new_angle}°")
        
    def process_controller_input(self, buttons, prev_buttons, hat, prev_hat):
        """Process controller inputs to control the arm"""
        # No inputs, do nothing
        if not buttons or len(buttons) < 12:  # Need enough buttons for A, B, X, Y, LB, RB
            return
            
        # # A button (index 0): Open claw
        # if buttons[0] == 1:
        #     self.open_claw()
                
        # # B button (index 1): Close claw
        # if buttons[1] == 1:
        #     self.close_claw()
                
        # X button (index 2): Stowed position
        if buttons[2] != prev_buttons[2] and buttons[2] == 1:
            self.set_state(ArmState.STOWED)
                
        # Y button (index 3): Fully out position
        if buttons[3] != prev_buttons[3] and buttons[3] == 1:
            self.set_state(ArmState.FULLY_OUT)
                
        # Right Bumper (index 5): Fully down position
        if len(buttons) > 5 and buttons[5] != prev_buttons[5] and buttons[5] == 1:
            self.set_state(ArmState.FULLY_DOWN)
                
        # Left Bumper (index 4): Out with elbow down position
        if len(buttons) > 4 and buttons[4] != prev_buttons[4] and buttons[4] == 1:
            self.set_state(ArmState.OUT_DOWN)
                
        # D-pad for continuous wrist rotation (hold to rotate)
        if hat and len(hat) > 0:
            if hat[0][0] == -1:  # Left on D-pad
                self.adjust_wrist(-1)  # Rotate left
            elif hat[0][0] == 1:  # Right on D-pad
                self.adjust_wrist(1)   # Rotate right

        # D-pad for continuous wrist rotation (hold to rotate)
        if hat and len(hat) > 0:
            if hat[0][1] == -1:  # Left on D-pad
                self.adjust_claw(-1)  # Rotate left
            elif hat[0][1] == 1:  # Right on D-pad
                self.adjust_claw(1)   # Rotate right

# --------------------------- Minimal ROV Class for Thruster Testing ---------------------------
class ROV:
    """Minimal ROV system for testing thruster functionality and Ethernet communication."""
    
    def __init__(self, stabilization_enabled=True):
        logger.info("Initializing ROV...")
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50
        
        #UNCOMMENT FOR IT TO WORK WITH TRUSTERS
        # Create thruster objects using a predefined channel map
        # self.thruster_channels = [13, 9, 10, 8, 11, 14, 12, 15]
        # self.thruster_names = [
        #     "FrontLeft", "FrontRight", "BackLeft", "BackRight",
        #     "FrontLeftUp", "FrontRightUp", "BackRightUp", "BackLeftUp"
        # ]
        # self.thrusters = []
        # for i, channel in enumerate(self.thruster_channels):
        #     name = self.thruster_names[i] if i < len(self.thruster_names) else f"Thruster{i}"
        #     self.thrusters.append(Thruster(channel, self.pca, name=name))

        self.thrusters = []

        self.controller_mapper = ControllerMapper()

        self.imu = IMUSensor()
        self.orientation_thread = None
        self.orientation_running = False
        self.current_heading = 0
        self.current_roll = 0
        self.current_pitch = 0

        self.left_x = 0.0
        self.left_y = 0.0
        self.right_x = 0.0
        self.right_y = 0.0
        self.left_trigger = 0.0
        self.right_trigger = 0.0

        # Create arm
        self.prev_button_states = {}
        self.arm = Arm(self.pca)

        self.chassis_control = ChassisControl()
        self.pid_lock = threading.Lock()  # For thread-safe PID updates
        self.stabilization_enabled = stabilization_enabled and self.imu.available
        
        # Initialize Ethernet Manager for network communication
        self.ethernet = EthernetManager(control_ip='192.168.1.237', control_port=4891)
        self.ethernet.set_control_callback(self.process_command)
        
        self.base_motor_states = [0.0] * 8
        self.pid_motor_adjustments = [0.0] * 8
        self.final_motor_states = [0.0] * 8
        self.last_command_time = time.time()
        self.running = False
        
        if self.stabilization_enabled:
            logger.info("PID stabilization is ENABLED")
        else:
            logger.info("PID stabilization is DISABLED")
        logger.info("Minimal ROV initialization complete")

    def start_orientation_thread(self):
        """Start a thread to continuously update orientation data."""
        if not self.imu.available:
            logger.warning("IMU not available, orientation thread not started")
            return False
            
        self.orientation_running = True
        self.orientation_thread = threading.Thread(target=self._orientation_updater)
        self.orientation_thread.daemon = True
        self.orientation_thread.start()
        logger.info("Orientation update thread started")
        return True
    
    def _orientation_updater(self):
        """Thread function to update orientation data."""
        logger.info("Orientation updater thread running")
        last_log_time = 0
        log_interval = 1.0  # Log IMU data every second
        
        while self.orientation_running:
            heading, roll, pitch = self.imu.get_orientation()
            
            with self.pid_lock:
                self.current_heading = heading
                self.current_roll = roll
                self.current_pitch = pitch
            
            # Log IMU data periodically
            current_time = time.time()
            if current_time - last_log_time > log_interval:
                # Get calibration status
                sys, gyro, accel, mag = self.imu.get_calibration_status()
                # logger.info(f"IMU Data - Heading: {heading:.2f}°, Roll: {roll:.2f}°, Pitch: {pitch:.2f}°")
                # logger.info(f"IMU Calibration - Sys: {sys}/3, Gyro: {gyro}/3, Accel: {accel}/3, Mag: {mag}/3")
                
                # Add IMU data to telemetry if a client is connected
                if self.ethernet.connected:
                    telemetry = {
                        "imu": {
                            "heading": heading,
                            "roll": roll,
                            "pitch": pitch,
                            "calibration": {
                                "sys": sys,
                                "gyro": gyro,
                                "accel": accel,
                                "mag": mag
                            }
                        }
                    }
                    self.ethernet.send_telemetry(telemetry)
                    
                last_log_time = current_time
            
            # Small sleep to prevent overwhelming the CPU
            time.sleep(0.01)
        logger.info("Orientation updater thread stopped")
    
    def start(self) -> None:
        """Start the ROV system."""
        logger.info("Starting ROV system...")
        
        # Initialize thrusters if any
        if self.thrusters:
            for thruster in self.thrusters:
                thruster.initialize()

        if self.imu.available:
            self.start_orientation_thread()
        self.ethernet.start_control_server()
        self.running = True
        self._main_loop()
    
    def _main_loop(self) -> None:
        """Main control loop for the ROV."""
        logger.info("Entering main loop...")
        
        while self.running:
            try:
                current_time = time.time()
                
                # Update motor states based on PID and arm mode
                self.update_motor_states()
    
                # Check for timeout (lost connection)
                if current_time - self.last_command_time > 5.0:
                    # Stop all motors if no commands received for 5 seconds
                    for thruster in self.thrusters:
                        thruster.set_speed(0.0)
                
                time.sleep(0.01)  # Small delay for loop iteration
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(0.5)
    
    def update_motor_states(self):
        """Update motor states based on control mode and PID."""

        imu_data = [
            0, 0, 0,  # X, Y, Z position defaults
            self.current_roll,
            self.current_pitch,
            self.current_heading
        ]
        
        # Apply PID adjustments if stabilization is enabled
        if self.stabilization_enabled and self.imu.available:
            with self.pid_lock:
                # Get current IMU data
                imu_data = [
                0, 0, 0,  # X, Y, Z position (not available from IMU, would need additional sensors)
                self.current_roll,
                self.current_pitch,
                self.current_heading
                ]
                
                # Log detailed IMU data for PID calculations
                logger.debug(f"PID Targets - Roll: 0.00°, Pitch: 0.00°, Yaw: {self.chassis_control.yaw_target:.2f}°")
                logger.debug(f"PID Current - Roll: {imu_data[3]:.2f}°, Pitch: {imu_data[4]:.2f}°, Heading: {imu_data[5]:.2f}°")
                
                # Calculate PID corrections - each individual PID controller will now log its details
                pid_corrections = self.chassis_control.PIDcorrection(imu_data)
                
                # Log final corrections after all PID calculations
                # logger.debug(f"PID Corrections Combined: [{', '.join([f'{x:.4f}' for x in pid_corrections])}]")
                
                controller = self.chassis_control.controllerInput(self.left_x, self.left_y, self.right_x, self.right_y, 
                                                                self.left_trigger, self.right_trigger)
                # logger.debug(f"Controller Input: [{', '.join([f'{x:.2f}' for x in controller])}]")

                vectorret = self.chassis_control.addVectors(controller, pid_corrections)
                # logger.debug(f"Combined Vector: [{', '.join([f'{x:.2f}' for x in vectorret])}]")

                # Convert PID corrections to motor adjustments
                self.final_motor_states = self.chassis_control.arcadeDrive6(vectorret)
                # logger.debug(f"Final Motor Values: [{', '.join([f'{x:.2f}' for x in self.final_motor_states])}]")
                
                # Normalize if any value exceeds limits
                max_val = max(abs(val) for val in self.final_motor_states)
                if max_val > 1.0:
                    self.final_motor_states = [val/max_val for val in self.final_motor_states]
        else:

            controller = self.chassis_control.controllerInput(self.left_x, self.left_y, self.right_x, self.right_y, 
                                                                  self.left_trigger, self.right_trigger)
            # Use base motor states without PID
            self.final_motor_states = self.chassis_control.arcadeDrive6(controller)

        max_val = max(abs(val) for val in self.final_motor_states)
        if max_val > 1.0:
            self.final_motor_states = [val/max_val for val in self.final_motor_states]
        # Apply motor states to thrusters
        if self.thrusters:
            for i, thruster in enumerate(self.thrusters):
                if i < len(self.final_motor_states):
                    thruster.set_speed(self.final_motor_states[i])
                
        self.chassis_control.updateTarget(
                        imu_data, self.left_x, self.left_y, self.right_x, self.right_y,
                        self.right_trigger, self.left_trigger
                    )
    def get_controller_mapping(self):
        """Return the current controller mapping for telemetry or UI"""
        return self.controller_mapper.get_current_mapping()
    

    def process_command(self, command_data):
        """Process received command data."""
        command_processed = False
        
        # Handle controller mapping commands
        if 'remap' in command_data:
            remap_data = command_data['remap']
            source = remap_data.get('source')
            target = remap_data.get('target')
            
            if source and target:
                self.controller_mapper.set_mapping(source, target)
                self.controller_mapper.save_mapping()
                command_processed = True
                return command_processed
            elif 'reset' in remap_data and remap_data['reset']:
                self.controller_mapper.reset_mapping()
                self.controller_mapper.save_mapping()
                command_processed = True
                return command_processed
        
        # Handle the controller data format
        if 'controller' in command_data:
            # Apply mapping to the controller data
            original_controller = command_data['controller']
            controller = self.controller_mapper.apply_mapping(original_controller)
            
            # Extract and store controller values
            self.left_x = controller.get('left_stick_x', 0.0)
            self.left_y = controller.get('left_stick_y', 0.0)
            self.right_x = controller.get('right_stick_x', 0.0)
            self.right_y = controller.get('right_stick_y', 0.0)
            self.left_trigger = controller.get('left_trigger', 0.0)
            self.right_trigger = controller.get('right_trigger', 0.0)
            
            # Apply deadzone
            def apply_deadzone(value, deadzone=0.05):
                return 0.0 if abs(value) < deadzone else value
                
            self.left_x = apply_deadzone(self.left_x)
            self.left_y = apply_deadzone(self.left_y)
            self.right_x = apply_deadzone(self.right_x)
            self.right_y = apply_deadzone(self.right_y)
            
            # Update PID targets if stabilization is enabled
            if self.stabilization_enabled and self.imu.available:
                with self.pid_lock:
                    imu_data = [0, 0, 0, self.current_roll, self.current_pitch, self.current_heading]
                    self.chassis_control.updateTarget(
                        imu_data, self.left_x, self.left_y, self.right_x, self.right_y,
                        self.right_trigger, self.left_trigger
                    )
            else:
                # Calculate motor values without PID
                controller_input = self.chassis_control.controllerInput(
                    self.left_x, self.left_y, self.right_x, self.right_y,
                    self.right_trigger, self.left_trigger
                )
                self.base_motor_states = self.chassis_control.arcadeDrive6(controller_input)

            # Save the current state before processing any new commands
            previous_state = self.arm.current_state
        
            # Get button states - these are now using the mapped controller data
            # Get button states - these are now using the mapped controller data
            a_button = controller.get('a', 0)
            b_button = controller.get('b', 0)
            x_button = controller.get('x', 0)
            y_button = controller.get('y', 0)
            lb_button = controller.get('lb', 0)
            rb_button = controller.get('rb', 0)
                        
            # Get previous button states
            prev_a = self.prev_button_states.get('a', 0)
            prev_b = self.prev_button_states.get('b', 0)
            prev_x = self.prev_button_states.get('x', 0)
            prev_y = self.prev_button_states.get('y', 0)
            prev_lb = self.prev_button_states.get('lb', 0)
            prev_rb = self.prev_button_states.get('rb', 0)

            # ADD THIS CODE BLOCK HERE - Special handling for remapped buttons
            # Check if any button is mapped to trigger another button's function
            for source, target in self.controller_mapper.mapping.items():
                if source in original_controller and original_controller[source] == 1:
                    if target == 'a': a_button = 1
                    elif target == 'b': b_button = 1
                    elif target == 'x': x_button = 1
                    elif target == 'y': y_button = 1
                    elif target == 'lb': lb_button = 1
                    elif target == 'rb': rb_button = 1
                    
                # Also update previous button states for proper edge detection
                if source in original_controller and self.prev_button_states.get(source, 0) == 1:
                    if target == 'a': prev_a = 1
                    elif target == 'b': prev_b = 1
                    elif target == 'x': prev_x = 1
                    elif target == 'y': prev_y = 1
                    elif target == 'lb': prev_lb = 1
                    elif target == 'rb': prev_rb = 1
            
            # Process button inputs for arm control - each check is independent
            if a_button == 1:
                self.arm.open_claw()
                command_processed = True
            if b_button == 1:
                self.arm.close_claw()
                command_processed = True

            # For state-changing buttons, only react on press (not hold)
            # and only if not already in that state
            # For state-changing buttons, now using if instead of elif
            # and removing the state check which causes issues with remapping
            if x_button == 1 and prev_x == 0:  # Removed state check
                self.arm.set_state(ArmState.STOWED)
                command_processed = True
            if y_button == 1 and prev_y == 0:  # Removed state check
                self.arm.set_state(ArmState.FULLY_OUT)
                command_processed = True
            if lb_button == 1 and prev_lb == 0:  # Removed state check
                self.arm.set_state(ArmState.OUT_DOWN)
                command_processed = True
            if rb_button == 1 and prev_rb == 0:  # Removed state check
                self.arm.set_state(ArmState.FULLY_DOWN)
                command_processed = True

            # Process D-pad (hat) inputs for wrist rotation and claw - CHANGED FROM elif to if
            dpad_x = controller.get('dpad_x', 0)
            dpad_y = controller.get('dpad_y', 0)
            if dpad_x == -1:  # Left on D-pad
                self.arm.adjust_wrist(-1)
                command_processed = True
            if dpad_x == 1:  # Right on D-pad
                self.arm.adjust_wrist(1)
                command_processed = True
            if dpad_y == -1:  # Down on D-pad
                self.arm.adjust_claw(-1)
                command_processed = True
            if dpad_y == 1:  # Up on D-pad
                self.arm.adjust_claw(1)
                command_processed = True
            
            # Update previous button states
            self.prev_button_states = {
                'a': a_button,
                'b': b_button,
                'x': x_button,
                'y': y_button,
                'lb': lb_button,
                'rb': rb_button
            }
        
        # Handle motor_values if present
        if 'motor_values' in command_data and self.thrusters:
            motor_values = command_data['motor_values']
            if isinstance(motor_values, list) and len(motor_values) == len(self.thrusters):
                # Check if values have changed significantly
                if any(abs(old - new) > 0.05 for old, new in zip(self.base_motor_states, motor_values)):
                    logger.info(f"New motor values received: {[f'{x:.2f}' for x in motor_values]}")
                    command_processed = True
                
                self.base_motor_states = motor_values
                
        # Update the last command time
        self.last_command_time = time.time()
        
        return command_processed
    
    def shutdown(self) -> None:
        """Shutdown the ROV system."""
        logger.info("Shutting down ROV system...")
        self.running = False
        
        # Stop thrusters if any
        if self.thrusters:
            for thruster in self.thrusters:
                thruster.stop()

        # Move the arm to a safe position
        try:
            self.arm.set_state(ArmState.STOWED)
            time.sleep(1)  # Wait for arm to reach position
        except Exception as e:
            logger.error(f"Error stowing arm during shutdown: {e}")

        # Clean up other resources
        if self.orientation_thread and self.orientation_thread.is_alive():
            self.orientation_thread.join(timeout=1.0)

        if self.imu.available:
            self.imu.close()

        self.ethernet.shutdown()
        self.pca.deinit()
        logger.info("ROV system shutdown complete")

# --------------------------- Main Entry Point ---------------------------
# Keep only this main function
def main():
    parser = argparse.ArgumentParser(description='ROV Control System with Arm and PID Stabilization')
    parser.add_argument('--disable-stabilization', action='store_true', help='Disable PID stabilization')
    parser.add_argument('--log-level', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')
    args = parser.parse_args()
    logging.getLogger().setLevel(args.log_level)
    
    rov = ROV(stabilization_enabled=not args.disable_stabilization)
    try:
        rov.start()
    except KeyboardInterrupt:
        logger.info("ROV interrupted by user")
    except Exception as e:
        logger.error(f"Error in ROV system: {e}")
    finally:
        rov.shutdown()

if __name__ == '__main__':
    main()