from smbus2 import SMBus
from time import sleep
import socket
import json
import time
import threading
import select
import logging
import argparse
from enum import Enum
import math

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

# --- Add BNO055 Import ---
try:
    # Assuming bno055.py is accessible (e.g., in the same directory or Python path)
    from bno055 import BNO055, BNO055_ADDRESS_A
    BNO055_AVAILABLE = True
    logger.info("BNO055 module successfully imported")
except ImportError:
    BNO055_AVAILABLE = False
    logger.error("Could not import BNO055 class. PID stabilization will be disabled.")
    BNO055 = None  # Define as None if import fails

# PCA9685 constants
PCA9685_ADDRESS = 0x40
MODE1 = 0x00
PRESCALE = 0xFE
LED0_ON_L = 0x06

# --------------------------- PID Controller Class ---------------------------
class PID:
    """PID controller for ROV stabilization."""
    def __init__(self, Kp, Ki, Kd, setpoint=0, sample_time=0.01, output_limits=(-1, 1)):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.setpoint = setpoint
        self.sample_time = sample_time
        self.output_limits = output_limits

        self._last_time = time.time()
        self._last_error = 0
        self._proportional = 0
        self._integral = 0
        self._derivative = 0
        self._last_output = 0
        
        logger.info(f"PID initialized with Kp={Kp}, Ki={Ki}, Kd={Kd}, setpoint={setpoint}")

    def update(self, current_value):
        """Update the PID controller with the current value and calculate control output."""
        current_time = time.time()
        delta_time = current_time - self._last_time

        if delta_time < self.sample_time:
            return self._last_output  # Return last output if sample time not elapsed

        error = self.setpoint - current_value
        
        # Handle heading wrap-around for yaw/heading PID
        if abs(error) > 180:
            error = error - 360 if error > 0 else error + 360
            
        delta_error = error - self._last_error

        self._proportional = self.Kp * error
        self._integral += self.Ki * error * delta_time
        
        # Clamp integral term
        if self.output_limits:
            min_out, max_out = self.output_limits
            self._integral = max(min(self._integral, max_out), min_out)

        self._derivative = 0
        if delta_time > 0:
            self._derivative = self.Kd * delta_error / delta_time

        output = self._proportional + self._integral + self._derivative

        # Clamp final output
        if self.output_limits:
            output = max(min(output, self.output_limits[1]), self.output_limits[0])

        self._last_error = error
        self._last_time = current_time
        self._last_output = output

        return output

    def reset(self):
        """Reset the PID controller state."""
        self._last_time = time.time()
        self._last_error = 0
        self._integral = 0
        self._derivative = 0
        self._last_output = 0
        logger.debug(f"PID reset - setpoint: {self.setpoint}")

    def set_gains(self, Kp, Ki, Kd):
        """Update the PID gains."""
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        logger.info(f"PID gains updated: Kp={Kp}, Ki={Ki}, Kd={Kd}")

    def set_setpoint(self, setpoint):
        """Update the PID setpoint."""
        self.setpoint = setpoint
        self.reset()  # Reset PID state when setpoint changes
        logger.info(f"PID setpoint updated to {setpoint}")

# --------------------------- PCA9685 Class ---------------------------
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
        sleep(0.001)  # micro-delay
        self.bus.write_byte_data(self.address, PRESCALE, prescale_val)
        sleep(0.001)  # micro-delay
        # Exit sleep mode
        self.bus.write_byte_data(self.address, MODE1, mode1)
        sleep(0.005)
        # Restart
        self.bus.write_byte_data(self.address, MODE1, mode1 | 0x80)
        sleep(0.001)  # micro-delay

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

        # Write each register with a small delay
        self.pca.bus.write_byte_data(self.pca.address, base_reg, on_value & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 1, (on_value >> 8) & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 2, off_value & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 3, (off_value >> 8) & 0xFF)
        time.sleep(0.001)

# --------------------------- Thruster Class ---------------------------
class Thruster:
    """Electronic Speed Controller (ESC) for thrusters."""
    def __init__(self, channel, pca, name="thruster"):
        self.channel = channel
        self.pca = pca
        self.name = name
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1100  # Reverse max pulse
        self.MAX_PULSE = 1900  # Forward max pulse
        self.FORWARD_MIN = 1525  # Minimum pulse to start forward motion
        self.REVERSE_MAX = 1475  # Maximum pulse to start reverse motion
        self.current_pulse = self.STOP_PULSE
        self.current_speed = 0.0  # Speed in range -1.0 to 1.0
        
        # For logging activity
        self.last_speed_change = time.time()
        self.total_active_time = 0.0
        self.direction_changes = 0
        logger.debug(f"Created thruster '{self.name}' on channel {self.channel}")

    def initialize(self):
        """Initialize ESC with neutral signal."""
        self._set_pulse_width(self.STOP_PULSE)
        sleep(2)
        logger.info(f"Thruster {self.name} on channel {self.channel} initialized")

    def set_speed(self, speed):
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
            logger.debug(f"Thruster {self.name}: {self.current_speed:.2f} -> {speed:.2f} (pulse: {int(pulse_width)})")
            self.current_speed = speed
            self.last_speed_change = now
            self._set_pulse_width(int(pulse_width))
        
    def _set_pulse_width(self, pulse_width):
        """Set ESC pulse width."""
        offset = 9
        pulse_width += offset
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        self.current_pulse = pulse_width
        sleep(0.001)

    def stop(self):
        """Stop the thruster."""
        prev_speed = self.current_speed
        self.set_speed(0.0)
        logger.info(f"Thruster {self.name} stopped (was: {prev_speed:.2f})")

    def get_stats(self):
        """Return statistics for this thruster."""
        return {
            "name": self.name,
            "channel": self.channel,
            "current_speed": self.current_speed,
            "current_pulse": self.current_pulse,
            "total_active_time": self.total_active_time,
            "direction_changes": self.direction_changes
        }
# --------------------------- IMU Sensor Class ---------------------------
class IMUSensor:
    """Interface to the BNO055 IMU sensor for orientation data."""
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
                    logger.error("Failed to initialize BNO055! PID will be inactive.")
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
    
    # In the IMUSensor class, modify the get_calibration_status method:
    def get_calibration_status(self):
        """Get current calibration status (sys, gyro, accel, mag)."""
        if self.available:
            try:
                # Use get_calibration instead of get_calibration_status
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

# --------------------------- ROV Class ---------------------------
class ROV:
    """ROV control system with PID stabilization."""
    
    def __init__(self, pid_enabled=True):
        logger.info("Initializing ROV...")
        
        # Initialize PCA9685 PWM controller
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50  # 50Hz is typical for ESCs
        
        # Create thruster objects using a predefined channel map
        # Indices correspond to esc_channels = [0, 7, 2, 5, 1, 4, 6, 3]
        # Horizontal: 0(FL), 7(FR), 2(BL), 5(BR)
        # Vertical:   1(FL_UP), 4(FR_UP), 6(BR_UP), 3(BL_UP)
        self.thruster_channels = [0, 7, 2, 5, 1, 4, 6, 3]
        self.thruster_names = [
            "FrontLeft", "FrontRight", "BackLeft", "BackRight",
            "FrontLeftUp", "FrontRightUp", "BackRightUp", "BackLeftUp"
        ]
        
        self.thrusters = []
        for i, channel in enumerate(self.thruster_channels):
            name = self.thruster_names[i] if i < len(self.thruster_names) else f"Thruster{i}"
            self.thrusters.append(Thruster(channel, self.pca, name=name))
        
        # Initialize IMU sensor
        self.imu = IMUSensor()
        self.orientation_thread = None
        self.orientation_running = False
        self.current_heading = 0
        self.current_roll = 0
        self.current_pitch = 0
        
        # Initialize PID controllers
        # Starting with conservative gains that can be tuned later
        self.pid_heading = PID(Kp=0.05, Ki=0.0, Kd=0.01, setpoint=0, sample_time=0.05, output_limits=(-0.5, 0.5))
        self.pid_pitch = PID(Kp=0.08, Ki=0.0, Kd=0.02, setpoint=0, sample_time=0.05, output_limits=(-0.5, 0.5))
        self.pid_roll = PID(Kp=0.08, Ki=0.0, Kd=0.02, setpoint=0, sample_time=0.05, output_limits=(-0.5, 0.5))
        
        # PID control flags
        self.pid_enabled = pid_enabled and self.imu.available
        self.pid_lock = threading.Lock()  # For thread-safe PID updates
        self.heading_pid_enabled = False  # Disable heading PID by default
        self.target_heading = None  # Will be set to current heading when enabled
        
        # Socket communication
        self.host = '192.168.1.237'  # Set to ROV's IP
        self.port = 4891
        self.server_socket = None
        self.client_socket = None
        self.running = False
        self.last_command_time = time.time()
        
        # Data processing
        self.base_motor_states = [0.0] * 8
        self.final_motor_states = [0.0] * 8
        
        logger.info("ROV initialization complete")
        
        if self.pid_enabled:
            logger.info("PID stabilization is ENABLED")
        else:
            logger.info("PID stabilization is DISABLED")
    
        # Add this method to the ROV class
    def log_debug_info(self):
        """Log detailed debug information about PID and motor states."""
        # Format motor values for better readability
        base_motors = [f"{x:.2f}" for x in self.base_motor_states]
        final_motors = [f"{x:.2f}" for x in self.final_motor_states]
        
        # Get PID adjustments
        heading_adj, pitch_adj, roll_adj = self.calculate_pid_adjustments()
        
        # Create debug message
        debug_info = (
            f"\n=== ROV Debug Info ===\n"
            f"Orientation: Heading={self.current_heading:.1f}° Roll={self.current_roll:.1f}° Pitch={self.current_pitch:.1f}°\n"
            f"Target Heading: {self.target_heading:.1f}°\n"
            f"PID Enabled: {self.pid_enabled}\n"
            f"PID Adjustments: Heading={heading_adj:.3f} Pitch={pitch_adj:.3f} Roll={roll_adj:.3f}\n"
            f"PID Outputs: Heading={self.pid_heading._last_output:.3f} Pitch={self.pid_pitch._last_output:.3f} Roll={self.pid_roll._last_output:.3f}\n"
            f"Heading PID Enabled: {self.heading_pid_enabled}\n"  # Add this line
            f"Base Motor States: {base_motors}\n"
            f"Final Motor States: {final_motors}\n"
            f"ESC Pulse Values: {[t.current_pulse for t in self.thrusters]}\n"
            f"=============================\n"
        )
        
        logger.info(debug_info)
        
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
        while self.orientation_running:
            heading, roll, pitch = self.imu.get_orientation()
            
            with self.pid_lock:
                self.current_heading = heading
                self.current_roll = roll
                self.current_pitch = pitch
                
                # Initialize target heading if needed
                if self.pid_enabled and self.target_heading is None:
                    self.target_heading = heading
                    self.pid_heading.set_setpoint(heading)
                    logger.info(f"Target heading initialized to {heading:.1f} degrees")
            
            # Small sleep to prevent overwhelming the CPU
            time.sleep(0.01)
            
        logger.info("Orientation updater thread stopped")
    
    def initialize_thrusters(self):
        """Initialize all thruster ESCs."""
        logger.info("Initializing all thrusters...")
        for thruster in self.thrusters:
            thruster.initialize()
        logger.info("All thrusters initialized")
    
    def start_server(self):
        """Start the control server to receive commands."""
        logger.info(f"Starting server on {self.host}:{self.port}...")
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        logger.info(f"Server listening on {self.host}:{self.port}")
        self.running = True
    
    def process_command(self, command_data):
        """Process received command data."""
        command_processed = False
        
        if 'motor_values' in command_data:
            motor_values = command_data['motor_values']
            if isinstance(motor_values, list) and len(motor_values) == len(self.thrusters):
                # Check if values have changed significantly
                if any(abs(old - new) > 0.05 for old, new in zip(self.base_motor_states, motor_values)):
                    logger.info(f"New motor values received: {[f'{x:.2f}' for x in motor_values]}")
                    command_processed = True
                
                self.base_motor_states = motor_values
                    
        if 'pid_enabled' in command_data:
            enable = bool(command_data['pid_enabled'])
            if enable != self.pid_enabled:
                self.set_pid_enabled(enable)
        
        # Add this new section to handle heading PID toggle
        if 'heading_pid_enabled' in command_data:
            enable = bool(command_data['heading_pid_enabled'])
            if enable != self.heading_pid_enabled:
                self.set_heading_pid_enabled(enable)       
                
        if 'pid_heading' in command_data:
            # Allow setting a specific target heading
            new_heading = float(command_data['pid_heading'])
            with self.pid_lock:
                self.target_heading = new_heading
                self.pid_heading.set_setpoint(new_heading)
                logger.info(f"Target heading updated to {new_heading:.1f}")
        
        if 'pid_gains' in command_data:
            # Format: {'heading': [Kp, Ki, Kd], 'pitch': [Kp, Ki, Kd], 'roll': [Kp, Ki, Kd]}
            gains = command_data['pid_gains']
            if 'heading' in gains and len(gains['heading']) == 3:
                self.pid_heading.set_gains(*gains['heading'])
            if 'pitch' in gains and len(gains['pitch']) == 3:
                self.pid_pitch.set_gains(*gains['pitch'])
            if 'roll' in gains and len(gains['roll']) == 3:
                self.pid_roll.set_gains(*gains['roll'])
                
        return command_processed
                
    def set_pid_enabled(self, enabled):
        """Enable or disable PID stabilization."""
        if enabled and not self.imu.available:
            logger.warning("Cannot enable PID: IMU not available")
            return False
            
        with self.pid_lock:
            if enabled:
                # Reset PIDs and initialize with current orientation
                heading, roll, pitch = self.imu.get_orientation()
                self.target_heading = heading
                self.pid_heading.set_setpoint(heading)
                self.pid_pitch.set_setpoint(0)  # We want to maintain level pitch
                self.pid_roll.set_setpoint(0)   # We want to maintain level roll
                self.pid_heading.reset()
                self.pid_pitch.reset()
                self.pid_roll.reset()
                
            self.pid_enabled = enabled
            logger.info(f"PID stabilization {'enabled' if enabled else 'disabled'} (heading control is disabled)")
            return True
    
    def set_heading_pid_enabled(self, enabled):
        """Enable or disable just the heading PID control."""
        with self.pid_lock:
            self.heading_pid_enabled = enabled and self.pid_enabled
            logger.info(f"Heading PID control {'enabled' if self.heading_pid_enabled else 'disabled'}")
            
    def calculate_pid_adjustments(self):
        """Calculate PID adjustments based on current orientation."""
        if not self.pid_enabled:
            return 0, 0, 0
            
        with self.pid_lock:
            # Calculate PID adjustments
            heading_adj = self.pid_heading.update(self.current_heading) if self.heading_pid_enabled else 0
            pitch_adj = self.pid_pitch.update(self.current_pitch)
            roll_adj = self.pid_roll.update(self.current_roll)
            
        return heading_adj, pitch_adj, roll_adj
    
    def mix_motors(self, base_states, heading_adj, pitch_adj, roll_adj):
        """Mix base motor commands with PID adjustments."""
        final_states = list(base_states)  # Start with joystick commands

        # --- Heading Adjustment (Yaw) ---
        # Affects horizontal thrusters for turning
        final_states[0] += heading_adj  # FL Horizontal
        final_states[2] += heading_adj  # BL Horizontal
        final_states[1] -= heading_adj  # FR Horizontal
        final_states[3] -= heading_adj  # BR Horizontal

        # --- Pitch Adjustment ---
        # Affects vertical thrusters (front vs back)
        final_states[4] += pitch_adj  # FL Vertical Up
        final_states[5] += pitch_adj  # FR Vertical Up
        final_states[7] -= pitch_adj  # BL Vertical Up
        final_states[6] -= pitch_adj  # BR Vertical Up

        # --- Roll Adjustment ---
        # Affects vertical thrusters (left vs right)
        final_states[4] += roll_adj  # FL Vertical Up
        final_states[7] += roll_adj  # BL Vertical Up
        final_states[5] -= roll_adj  # FR Vertical Up
        final_states[6] -= roll_adj  # BR Vertical Up

        # Clamp all final states between -1.0 and 1.0
        final_states = [max(min(state, 1.0), -1.0) for state in final_states]
        return final_states
    
    def update_thrusters(self):
        """Update thruster speeds based on current commands and PID adjustments."""
        # Calculate PID adjustments if enabled
        heading_adj, pitch_adj, roll_adj = self.calculate_pid_adjustments()
        
         # Store previous motor states for change detection
        previous_motor_states = self.final_motor_states.copy()
            
        # Mix motor commands
        self.final_motor_states = self.mix_motors(
            self.base_motor_states,
            heading_adj,
            pitch_adj,
            roll_adj
        )
        
        # Set thruster speeds
        for i, thruster in enumerate(self.thrusters):
            thruster.set_speed(self.final_motor_states[i])
         #Log when motor commands change significantly
        if any(abs(prev - curr) > 0.05 for prev, curr in zip(previous_motor_states, self.final_motor_states)):
            self.log_debug_info()
        
    def run(self):
        """Main ROV control loop."""
        try:
            # Initialize hardware
            self.initialize_thrusters()
            
            # Start orientation updates if IMU available
            if self.imu.available:
                self.start_orientation_thread()
                
            # Start server
            self.start_server()
            
            # Main control loop
            last_status_time = time.time()
            
            logger.info("ROV running. Waiting for client connection...")
            
            while self.running:
                # Wait for client connection
                self.server_socket.settimeout(1.0)
                try:
                    self.client_socket, client_address = self.server_socket.accept()
                    logger.info(f"Client connected from {client_address}")
                    self.last_command_time = time.time()
                    
                    # Reset PID target when new client connects
                    if self.pid_enabled:
                        with self.pid_lock:
                            heading, _, _ = self.imu.get_orientation()
                            self.target_heading = heading
                            self.pid_heading.set_setpoint(heading)
                            logger.info(f"Reset target heading to {heading:.1f} degrees for new client")
                    
                    # Handle client communication
                    self._handle_client()
                    
                except socket.timeout:
                    # No client connected yet, continue waiting
                    continue
                except KeyboardInterrupt:
                    logger.info("ROV operation interrupted by user")
                    break
                except Exception as e:
                    logger.error(f"Error in server accept: {e}")
                    time.sleep(1)  # Prevent tight loop on error
                    
            logger.info("ROV control loop ended")
                
        except KeyboardInterrupt:
            logger.info("ROV operation interrupted by user")
        except Exception as e:
            logger.error(f"Error in ROV operation: {e}")
        finally:
            self.shutdown()
    
    def _handle_client(self):
        """Handle communication with a connected client."""
        self.client_socket.settimeout(0.5)  # Set socket timeout
        
        #Initialize the last_status_time here
        last_status_time = time.time()
        last_activity_check = time.time()
        last_debug_time = time.time()  # Add this line to initialize last_debug_time
        
        while self.running:
            try:
                # Check for incoming data
                ready = select.select([self.client_socket], [], [], 0.05)
                if ready[0]:
                    data = self.client_socket.recv(1024)
                    if not data:
                        logger.info("Client disconnected")
                        break
                        
                    # Process received data
                    try:
                        command_data = json.loads(data.decode('utf-8'))
                        self.process_command(command_data)
                        self.last_command_time = time.time()
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON received: {e}")
                    except Exception as e:
                        logger.error(f"Error processing command: {e}")
                
                # Check for client timeout (5 seconds without commands)
                if time.time() - self.last_command_time > 5.0:
                    logger.warning("Client connection timed out (no commands received)")
                    break
                    
                # Update thruster values based on commands and PID
                self.update_thrusters()
                
                # Send telemetry data periodically (every 200ms)
                current_time = time.time()
                if current_time - last_status_time >= 0.2:
                    self._send_telemetry()
                    last_status_time = current_time
                
                # Log debug info periodically (every 2 seconds)
                if current_time - last_debug_time >= 2.0:
                    self.log_debug_info()
                    last_debug_time = current_time
                
                # Send telemetry data periodically (every 200ms)
                current_time = time.time()
                if current_time - last_status_time >= 0.2:
                    self._send_telemetry()
                    last_status_time = current_time
                
                # Check thruster activity periodically (every 3 seconds)
                if current_time - last_activity_check >= 3.0:
                    self.monitor_thruster_activity()
                    last_activity_check = current_time
                    
            except socket.timeout:
                # Socket timeout - continue loop
                continue
            except Exception as e:
                logger.error(f"Error in client handler: {e}")
                break
                
        # Close client socket when done
        try:
            self.client_socket.close()
        except Exception:
            pass
        self.client_socket = None
        
        # Stop thrusters when client disconnects
        for thruster in self.thrusters:
            thruster.stop()
        logger.info("All thrusters stopped after client disconnect")
    
    def _send_telemetry(self):
        """Send telemetry data to the connected client."""
        if not self.client_socket:
            return
            
        # Prepare telemetry data
        telemetry = {
            "timestamp": time.time(),
            "orientation": {
                "heading": self.current_heading,
                "roll": self.current_roll,
                "pitch": self.current_pitch
            },
            "target_heading": self.target_heading,
            "pid_enabled": self.pid_enabled,
            "heading_pid_enabled": self.heading_pid_enabled,  # Add this line
            "calibration": self.imu.get_calibration_status() if self.imu.available else (0, 0, 0, 0),
            "thrusters": [t.current_speed for t in self.thrusters],
            "pid_output": {
                "heading": self.pid_heading._last_output if self.pid_enabled else 0,
                "pitch": self.pid_pitch._last_output if self.pid_enabled else 0,
                "roll": self.pid_roll._last_output if self.pid_enabled else 0
            }
        }
        
        try:
            self.client_socket.send(json.dumps(telemetry).encode('utf-8'))
        except Exception as e:
            logger.error(f"Error sending telemetry: {e}")
            
    def monitor_thruster_activity(self):
        """Report on thruster activity in the last few seconds."""
        active_thrusters = []
        for i, thruster in enumerate(self.thrusters):
            if abs(thruster.current_speed) > 0.01:  # If thruster is not at zero
                active_thrusters.append(f"{thruster.name}({thruster.current_speed:.2f})")
        
        if active_thrusters:
            logger.info(f"Active thrusters: {', '.join(active_thrusters)}")
        else:
            logger.info("All thrusters idle")

    def shutdown(self):
        """Safely shut down the ROV system."""
        logger.info("Shutting down ROV...")
        
        # Stop thrusters
        logger.info("Stopping all thrusters...")
        for thruster in self.thrusters:
            thruster.stop()
        
        # Stop threads
        self.running = False
        self.orientation_running = False
        if self.orientation_thread and self.orientation_thread.is_alive():
            self.orientation_thread.join(timeout=1.0)
        
        # Close connections
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
                
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        
        # Close hardware
        logger.info("Deinitializing PCA9685...")
        self.pca.deinit()
        
        if self.imu.available:
            logger.info("Closing IMU connection...")
            self.imu.close()
            
        logger.info("ROV shutdown complete")

# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description='ROV Control System with PID Stabilization')
    parser.add_argument('--disable-pid', action='store_true', help='Disable PID stabilization')
    parser.add_argument('--disable-heading-pid', action='store_true', help='Disable only heading PID stabilization')
    parser.add_argument('--log-level', type=str, default='INFO',
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                      help='Logging level')
    args = parser.parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(args.log_level)
    
    # Create and run the ROV
    rov = ROV(pid_enabled=not args.disable_pid)
    
    # Apply heading-specific setting
    if args.disable_heading_pid:
        rov.heading_pid_enabled = False
        logger.info("Heading PID disabled via command-line option")
        
    try:
        rov.run()
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
    finally:
        rov.shutdown()
        logger.info("Program terminated")

if __name__ == '__main__':
    main()