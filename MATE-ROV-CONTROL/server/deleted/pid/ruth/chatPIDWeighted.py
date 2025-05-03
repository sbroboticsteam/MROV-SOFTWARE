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
import os

from rov.hardware.pca9685 import PCA9685
from classesForChatPID.thruster import Thruster
from classesForChatPID.imu_sensor import IMUSensor
from rov.ethernet_manager import EthernetManager

def arcadeDrive3(x, y, rx, ry, rT, lT) -> list[int]:
    """
    Convert controller inputs to thruster values
    x: left/right movement (left stick X)
    y: forward/backward movement (left stick Y)
    rx: yaw/turning (right stick X)
    ry: pitch control (right stick Y) - NEW!
    rT: up movement (right trigger)
    lT: down movement (left trigger)
    """
    # Calculate vertical thrust from triggers
    PWM = rT - lT
    
    # Calculate horizontal thruster values with X, Y, and rotation inputs
    frontLeft = y + x + rx  # 2
    frontRight = y - x - rx  # 3
    backRight = -y - x + rx  # 4  
    backLeft = -y + x - rx   # 1
    
    # Create initial data array for horizontal thrusters
    data = [-frontLeft, -frontRight, -backLeft, -backRight]
    
    # Normalize thruster values if any exceeds limits
    max_val = max(abs(val) for val in data)
    if max_val > 1.0:
        data = [val/max_val for val in data]
    
    # Apply pitch control to vertical thrusters
    # When ry is positive (stick down), front should go down, back should go up
    front_vertical = -PWM - ry
    back_vertical = -PWM + ry
    
    # Add vertical thrusters to the data array
    data.append(front_vertical)  # Front Left Up
    data.append(front_vertical)  # Front Right Up
    data.append(back_vertical)   # Back Right Up
    data.append(back_vertical)   # Back Left Up
    
    return data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

# Path to the PID calibration file
DEFAULT_PID_CALIBRATION_FILE = "pid_auto_calibration.json"

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

# --------------------------- ROV Class ---------------------------
class ROV:
    """ROV control system with PID stabilization."""
    
    def __init__(self, pid_enabled=True, pid_weight=1.0, calibration_file=None):
        logger.info("Initializing ROV...")
        
        # Initialize PCA9685 PWM controller
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50  # 50Hz is typical for ESCs
        
        # Create thruster objects using a predefined channel map
        # Indices correspond to esc_channels = [0, 7, 2, 5, 1, 4, 6, 3]
        # Horizontal: 0(FL), 7(FR), 2(BL), 5(BR)
        # Vertical:   1(FL_UP), 4(FR_UP), 6(BR_UP), 3(BL_UP)
        # after
        # after
        self.thruster_channels = [13, 9, 10, 8, 11, 14, 12, 15]
        self.thruster_names    = [
            "FrontLeft", "FrontRight", "BackLeft", "BackRight",
            "FrontLeftUp", "FrontRightUp", "BackLeftUp", "BackRightUp"
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
        
        # Load PID calibration values if available
        pid_gains = self.load_pid_calibration(calibration_file)
        
        # Initialize PID controllers with calibration values or defaults
        heading_gains = pid_gains.get('heading_pid', {'Kp': 0.05, 'Ki': 0.0, 'Kd': 0.01})
        pitch_gains = pid_gains.get('pitch_pid', {'Kp': 0.08, 'Ki': 0.0, 'Kd': 0.02})
        roll_gains = pid_gains.get('roll_pid', {'Kp': 0.08, 'Ki': 0.0, 'Kd': 0.02})
        
        self.pid_heading = PID(
            Kp=heading_gains['Kp'], 
            Ki=heading_gains['Ki'], 
            Kd=heading_gains['Kd'], 
            setpoint=0, 
            sample_time=0.05, 
            output_limits=(-0.5, 0.5)
        )
        
        self.pid_pitch = PID(
            Kp=pitch_gains['Kp'], 
            Ki=pitch_gains['Ki'], 
            Kd=pitch_gains['Kd'], 
            setpoint=0, 
            sample_time=0.05, 
            output_limits=(-0.5, 0.5)
        )
        
        self.pid_roll = PID(
            Kp=roll_gains['Kp'], 
            Ki=roll_gains['Ki'], 
            Kd=roll_gains['Kd'], 
            setpoint=0, 
            sample_time=0.05, 
            output_limits=(-0.5, 0.5)
        )
        
        # PID control flags
        self.pid_enabled = pid_enabled and self.imu.available
        self.pid_lock = threading.Lock()  # For thread-safe PID updates
        self.heading_pid_enabled = False  # Disable heading PID by default
        self.target_heading = None  # Will be set to current heading when enabled
        
        # PID weight factor (0-1)
        self.pid_weight = max(0.0, min(1.0, pid_weight))
        logger.info(f"PID weight set to {self.pid_weight:.2f}")
        
        # Network communication via EthernetManager
        self.ethernet = EthernetManager(control_ip='192.168.1.237', control_port=4891)
        self.ethernet.set_control_callback(self.process_command)
        
        # Data processing
        self.base_motor_states = [0.0] * 8
        self.final_motor_states = [0.0] * 8
        self.running = False
        self.last_command_time = time.time()
        
        logger.info("ROV initialization complete")
        
        if self.pid_enabled:
            logger.info("PID stabilization is ENABLED")
        else:
            logger.info("PID stabilization is DISABLED")

    def load_pid_calibration(self, calibration_file=None):
        """Load PID calibration values from a JSON file."""
        if calibration_file is None:
            calibration_file = DEFAULT_PID_CALIBRATION_FILE
            
        try:
            # Get the full path to the calibration file
            if not os.path.isabs(calibration_file):
                # Try in the current directory first
                if os.path.exists(calibration_file):
                    full_path = calibration_file
                else:
                    # Try in the same directory as this script
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    full_path = os.path.join(script_dir, calibration_file)
            else:
                full_path = calibration_file
                
            if not os.path.exists(full_path):
                logger.warning(f"PID calibration file not found: {full_path}")
                return {}
                
            with open(full_path, 'r') as f:
                calibration = json.load(f)
                logger.info(f"Loaded PID calibration from {full_path}")
                return calibration
                
        except Exception as e:
            logger.error(f"Error loading PID calibration: {e}")
            return {}
    
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
            f"PID Weight: {self.pid_weight:.2f}\n"
            f"PID Adjustments: Heading={heading_adj:.3f} Pitch={pitch_adj:.3f} Roll={roll_adj:.3f}\n"
            f"PID Outputs: Heading={self.pid_heading._last_output:.3f} Pitch={self.pid_pitch._last_output:.3f} Roll={self.pid_roll._last_output:.3f}\n"
            f"Heading PID Enabled: {self.heading_pid_enabled}\n"
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
    
    def process_command(self, command_data):
        """Process received command data."""
        command_processed = False
        
        # Handle the controller data format from com_socket_server_test.py
        if 'controller' in command_data:
            controller = command_data['controller']
            
            # Extract controller values
            left_x = controller.get('left_stick_x', 0.0)
            left_y = controller.get('left_stick_y', 0.0)
            right_x = controller.get('right_stick_x', 0.0)
            right_y = controller.get('right_stick_y', 0.0)
            left_trigger = controller.get('left_trigger', 0.0)
            right_trigger = controller.get('right_trigger', 0.0)
            
            # Apply deadzone to avoid drift
            def apply_deadzone(value, deadzone=0.05):
                return 0.0 if abs(value) < deadzone else value
                
            left_x = apply_deadzone(left_x)
            left_y = apply_deadzone(left_y)
            right_x = apply_deadzone(right_x)
            right_y = apply_deadzone(right_y)
            
            # Convert controller values to motor values using our updated function
            motor_values = arcadeDrive3(
                left_x, 
                -left_y,  # Invert Y-axis if needed (check your control scheme)
                right_x,
                -right_y, # Invert Y-axis if needed
                right_trigger,
                left_trigger
            )
            
            # Set the base motor states
            self.base_motor_states = motor_values
        command_processed = True
    
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
        
        if 'heading_pid_enabled' in command_data:
            enable = bool(command_data['heading_pid_enabled'])
            if enable != self.heading_pid_enabled:
                self.set_heading_pid_enabled(enable)
        
        if 'pid_weight' in command_data:
            weight = float(command_data['pid_weight'])
            weight = max(0.0, min(1.0, weight))  # Clamp between 0 and 1
            if weight != self.pid_weight:
                self.pid_weight = weight
                logger.info(f"PID weight updated to {weight:.2f}")
                
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
                
        # Update the last command time
        self.last_command_time = time.time()
        
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
            
            # Apply PID weight factor
            heading_adj *= self.pid_weight
            pitch_adj *= self.pid_weight
            roll_adj *= self.pid_weight
            
        return heading_adj, pitch_adj, roll_adj
    
    def mix_motors(self, base_states, heading_adj, pitch_adj, roll_adj):
        """Mix base motor commands with PID adjustments, accounting for 45° motor placement."""
        final_states = list(base_states)  # Start with joystick commands

        # --- Heading Adjustment (Yaw) ---
        # For 45° placed thrusters, we need to adjust the thrust vectors
        # For clockwise rotation (positive heading_adj):
        #   FL(-45°) and BR(135°) thrusters should push forward (+)
        #   FR(45°) and BL(-135°) thrusters should push backward (-)
        
        # Front Left (-45°) and Back Right (135°)
        final_states[0] += heading_adj  # FL
        final_states[3] += heading_adj  # BR
        
        # Front Right (45°) and Back Left (-135°)
        final_states[1] -= heading_adj  # FR
        final_states[2] -= heading_adj  # BL

        # Pitch: front ups ↑, back ups ↓
        for i in (4,5): final_states[i] +=  pitch_adj
        for i in (6,7): final_states[i] -=  pitch_adj

        # Roll: left ups ↑, right ups ↓
        for i in (4,7): final_states[i] +=  roll_adj
        for i in (5,6): final_states[i] -=  roll_adj

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
            
        # Log when motor commands change significantly
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
                
            # Start network server via EthernetManager
            self.ethernet.start_control_server()
            self.running = True
            
            logger.info("ROV running. Waiting for client connection...")
            
            # Main control loop variables
            last_status_time = time.time()
            last_activity_check = time.time()
            last_debug_time = time.time()
            
            while self.running:
                current_time = time.time()
                
                # If a client connects, reset heading target
                if self.ethernet.connected and self.pid_enabled and self.target_heading is None:
                    with self.pid_lock:
                        heading, _, _ = self.imu.get_orientation()
                        self.target_heading = heading
                        self.pid_heading.set_setpoint(heading)
                        logger.info(f"Reset target heading to {heading:.1f} degrees for new client")
                
                # Update thruster values based on commands and PID
                self.update_thrusters()
                
                # Send telemetry data periodically (every 200ms)
                if current_time - last_status_time >= 0.2:
                    self._send_telemetry()
                    last_status_time = current_time
                
                # Log debug info periodically (every 2 seconds)
                if current_time - last_debug_time >= 2.0:
                    self.log_debug_info()
                    last_debug_time = current_time
                
                # Check thruster activity periodically (every 3 seconds)
                if current_time - last_activity_check >= 3.0:
                    self.monitor_thruster_activity()
                    last_activity_check = current_time
                    
                # Check for client timeout (5 seconds without commands)
                if self.ethernet.connected and (current_time - self.last_command_time > 5.0):
                    logger.warning("Client connection timed out (no commands received)")
                    # Connection will be handled by the EthernetManager
                    
                # Small sleep to prevent CPU hogging
                time.sleep(0.01)
                    
        except KeyboardInterrupt:
            logger.info("ROV operation interrupted by user")
        except Exception as e:
            logger.error(f"Error in ROV operation: {e}")
        finally:
            self.shutdown()
    
    def _send_telemetry(self):
        """Send telemetry data to the connected client."""
        if not self.ethernet.connected:
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
            "heading_pid_enabled": self.heading_pid_enabled,
            "pid_weight": self.pid_weight,
            "calibration": self.imu.get_calibration_status() if self.imu.available else (0, 0, 0, 0),
            "thrusters": [t.current_speed for t in self.thrusters],
            "pid_output": {
                "heading": self.pid_heading._last_output if self.pid_enabled else 0,
                "pitch": self.pid_pitch._last_output if self.pid_enabled else 0,
                "roll": self.pid_roll._last_output if self.pid_enabled else 0
            }
        }
        
        # Send telemetry via ethernet manager
        try:
            self.ethernet._send_data(json.dumps(telemetry).encode('utf-8'))
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
        
        # Close network connections
        self.ethernet.shutdown()
        
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
    parser.add_argument('--pid-weight', type=float, default=1.0, 
                      help='PID influence weight (0.0-1.0)')
    parser.add_argument('--pid-calibration', type=str, default=DEFAULT_PID_CALIBRATION_FILE,
                      help=f'Path to PID calibration file (default: {DEFAULT_PID_CALIBRATION_FILE})')
    parser.add_argument('--log-level', type=str, default='INFO',
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                      help='Logging level')
    args = parser.parse_args()

    # python ChatPIDWeighted.py --disable-heading-pid --pid-weight 0.8
    
    # Set logging level
    logging.getLogger().setLevel(args.log_level)
    
    # Validate and clamp PID weight
    pid_weight = max(0.0, min(1.0, args.pid_weight))
    if pid_weight != args.pid_weight:
        logger.warning(f"PID weight clamped to valid range: {pid_weight}")
    
    # Create and run the ROV with calibration file
    rov = ROV(
        pid_enabled=not args.disable_pid, 
        pid_weight=pid_weight,
        calibration_file=args.pid_calibration
    )
    
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