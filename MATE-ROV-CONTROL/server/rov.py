from smbus2 import SMBus
from time import sleep
import socket
import json
import time
import threading
from enum import Enum
import logging
import random
from typing import Dict, List, Tuple, Optional, Any
from imuSensor import IMUManager 
from depth import DepthSensor
import math

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

class PCA9685:
    """Hardware driver for PCA9685 PWM controller"""
    
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
        except:
            pass

class PCA9685Channel:
    """Individual channel on the PCA9685 PWM controller"""
    
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

class Servo:
    """Generic servo motor controller"""
    
    def __init__(self, channel: int, pca: PCA9685, min_pulse: int = 900, max_pulse: int = 2100, name: str = "unnamed"):
        self.channel = channel
        self.pca = pca
        self.min_pulse = min_pulse
        self.max_pulse = max_pulse
        self.current_pulse = 1500  # Neutral position
        self.name = name
        self.last_angle = 90  # Default to middle position
        
    def set_angle(self, angle: float) -> None:
        """Set servo position using angle (0-180°)"""
        # Ensure angle is within bounds
        angle = max(0, min(180, angle)) #TODO change to 270
        # Convert angle to value (-1 to 1)
        value = (angle / 90.0) - 1.0
        # Map value to pulse width
        pulse_width = self._map_value_to_pulse(value)
        self._set_pulse_width(pulse_width)
        self.last_angle = angle
        logger.debug(f"Servo {self.name}: set to angle {angle}°")
        
    def _map_value_to_pulse(self, value: float) -> int:
        """Map a value from -1,1 to min_pulse,max_pulse"""
        value = max(-1.0, min(1.0, value))  # Ensure value is in range
        return int(self.min_pulse + (value + 1) * (self.max_pulse - self.min_pulse) / 2)
        
    def _set_pulse_width(self, pulse_width: int) -> None:
        """Set the servo pulse width directly"""
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        logger.debug(f"{self.name} (Ch {self.channel}): {pulse_width} µs -> duty {duty_cycle}")
        self.current_pulse = pulse_width
        time.sleep(0.001)  # Small delay to help register changes

class Thruster:
    """Electronic Speed Controller (ESC) for thrusters"""
    
    def __init__(self, channel: int, pca: PCA9685, name: str = "thruster"):
        self.channel = channel
        self.pca = pca
        self.name = name
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1300  # Reverse maximum
        self.MAX_PULSE = 1700  # Forward maximum
        self.FORWARD_MIN = 1525  # Minimum pulse to start moving forward
        self.REVERSE_MAX = 1475  # Maximum pulse to start moving reverse
        self.current_pulse = self.STOP_PULSE
        self.current_speed = 0.0  # Range: -1.0 to 1.0
        
        # Add timestamp for logging thruster activity
        self.last_speed_change = time.time()
        self.total_active_time = 0.0
        self.direction_changes = 0
        
        logger.debug(f"Created thruster '{self.name}' on channel {self.channel}")

    def initialize(self) -> None:
        """Initialize the ESC with the neutral signal"""
        self._set_pulse_width(self.STOP_PULSE)
        sleep(2)
        logger.info(f"Thruster {self.name} on channel {self.channel} initialized")

    def set_speed(self, speed: float) -> None:
        """
        Set thruster speed from -1.0 (full reverse) to 1.0 (full forward)
        0.0 is stopped
        """
        # Limit speed to -1.0 to 1.0
        speed = max(-1.0, min(1.0, speed))
        
        # Calculate pulse width based on speed
        if speed > 0:
            pulse_width = self.FORWARD_MIN + (speed * (self.MAX_PULSE - self.FORWARD_MIN))
        elif speed < 0:
            pulse_width = self.REVERSE_MAX - (abs(speed) * (self.REVERSE_MAX - self.MIN_PULSE))
        else:
            pulse_width = self.STOP_PULSE
            
        # Log direction changes
        if (self.current_speed > 0 and speed < 0) or (self.current_speed < 0 and speed > 0):
            self.direction_changes += 1
            logger.debug(f"Thruster {self.name}: Direction change #{self.direction_changes}")
            
        # Only update if speed has changed
        if speed != self.current_speed:
            now = time.time()
            
            # Update active time counter if thruster was active
            if self.current_speed != 0:
                active_time = now - self.last_speed_change
                self.total_active_time += active_time
                
            # Log the speed change
            logger.info(f"Thruster {self.name}: {self.current_speed:.2f} → {speed:.2f} (pulse: {int(pulse_width)})")
            
            self.current_speed = speed
            self.last_speed_change = now
            self._set_pulse_width(int(pulse_width))
        
    def _set_pulse_width(self, pulse_width: int) -> None:
        """Set the ESC pulse width directly"""
        offset = 9
        pulse_width += offset
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        self.current_pulse = pulse_width
        time.sleep(0.001)  # Small delay to help register changes

    def stop(self) -> None:
        """Stop the thruster"""
        prev_speed = self.current_speed
        self.set_speed(0.0)
        logger.info(f"Thruster {self.name} stopped (was: {prev_speed:.2f})")
        
    def get_stats(self) -> Dict:
        """Get statistics for this thruster"""
        return {
            "name": self.name,
            "channel": self.channel,
            "current_speed": self.current_speed,
            "current_pulse": self.current_pulse,
            "total_active_time": self.total_active_time,
            "direction_changes": self.direction_changes
        }

class ArmState(Enum):
    """State enum for arm positions"""
    STOWED = 0      # Arm in storage/travel position
    FULLY_OUT = 1   # Arm fully extended straight out
    FULLY_DOWN = 2  # Arm fully down
    OUT_DOWN = 3    # Arm out with elbow down

class Arm: #TODO use mapping not buttons directly
    """Robotic arm with four servos: claw, wrist, elbow, and shoulder"""
    
    # Default angle presets for each position
    POSITIONS = {
        ArmState.STOWED: {
            "claw": 180,     # Closed position (2100 µs)
            "wrist": 0,      # Horizontal rotation (900 µs)
            "elbow": 10,     # Up position (850 µs)
            "shoulder": 10   # Hidden away (900 µs)
        },
        ArmState.FULLY_OUT: {
            "claw": 0,       # Open position (500 µs)
            "wrist": 90,     # Vertical (1450 µs)
            "elbow": 80,     # Straight out (1250 µs)
            "shoulder": 140  # Extended out (1600 µs)
        },
        ArmState.FULLY_DOWN: {
            "claw": 0,       # Open position (500 µs) 
            "wrist": 90,     # Vertical (1450 µs)
            "elbow": 140,    # Down position (1600 µs)
            "shoulder": 80   # Down position (1125 µs)
        },
        ArmState.OUT_DOWN: {
            "claw": 0,       # Open position (500 µs)
            "wrist": 90,     # Vertical (1450 µs)
            "elbow": 140,    # Down position (1600 µs)
            "shoulder": 140  # Extended out (1600 µs)
        }
    }
    
    def __init__(self, pca: PCA9685):
        """Initialize the arm with all servos"""
        self.pca = pca
        self.current_state = ArmState.STOWED
        
        # Create servo objects with channel assignments
        self.servos = {
            "claw": Servo(0, pca, min_pulse=500, max_pulse=2100, name="Claw"),
            "wrist": Servo(1, pca, min_pulse=900, max_pulse=2000, name="Wrist"),
            "elbow": Servo(2, pca, min_pulse=850, max_pulse=1600, name="Elbow"),
            "shoulder": Servo(3, pca, min_pulse=900, max_pulse=1600, name="Shoulder")
        }
        
        # Current wrist rotation angle for incremental control
        self.current_wrist_angle = 90
        logger.info("Arm component initialized")
        
    def initialize(self) -> None:
        """Initialize all arm servos to stowed position"""
        logger.info("Initializing arm to stowed position...")
        self.set_state(ArmState.STOWED)
        logger.info("Arm initialization complete")
        
    def set_state(self, state: ArmState) -> bool: #do conditional ordering for the servos when doing set states
        """Set the arm to a predefined state"""
        if state not in ArmState:
            logger.error(f"Invalid arm state: {state}")
            return False
            
        logger.info(f"Setting arm to {state.name} position...")
        
        # Get the preset positions for this state
        positions = self.POSITIONS[state]
        
        # Set each servo to its position with a small delay between each
        for servo_name, angle in positions.items():
            # Skip wrist adjustment if already at target angle
            if (servo_name == "wrist" and abs(self.current_wrist_angle - angle) < 5):
                continue
                
            self.servos[servo_name].set_angle(angle)
            
            # Update current wrist angle if we're adjusting it
            if (servo_name == "wrist"):
                self.current_wrist_angle = angle
                
            sleep(0.1)  # Small delay between servo movements
            
        self.current_state = state
        logger.info(f"Arm now in {state.name} position")
        return True
        
    def open_claw(self) -> None: #bumpers for open and close
        """Open the claw"""
        self.servos["claw"].set_angle(0)  # 0° = open
        logger.info("Claw opened")
        
    def close_claw(self) -> None:
        """Close the claw"""
        self.servos["claw"].set_angle(180)  # 180° = closed
        logger.info("Claw closed")
        
    def adjust_wrist(self, direction: int, step: int = 5) -> None: #TODO MAKEIT SO THAT IT IS HOLD TO MOVE (dpads to be set states)
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
            logger.info(f"Wrist rotated to {new_angle}°")
    
    def process_controller_input(self, buttons: List[int], prev_buttons: List[int], 
                                hat: List[Tuple[int, int]], prev_hat: List[Tuple[int, int]]) -> None:
        """Process controller inputs to control the arm"""
        # No inputs, do nothing
        if not buttons or len(buttons) < 12:  # Need enough buttons for A, B, X, Y, LB, RB
            return
            
        # A button (index 0): Open claw
        if buttons[0] == 1:
            self.open_claw()
                
        # B button (index 1): Close claw
        if buttons[1] == 1:
            self.close_claw()
                
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

    def shutdown(self) -> None:
        """Safely stow the arm for shutdown"""
        logger.info("Arm shutting down - stowing...")
        self.set_state(ArmState.STOWED)
        logger.info("Arm stowed")

class PIDController:
    """Generic PID controller for stability and movement control"""
    
    def __init__(self, kp: float = 1.0, ki: float = 0.0, kd: float = 0.0):
        self.kp = kp  # Proportional gain
        self.ki = ki  # Integral gain
        self.kd = kd  # Derivative gain
        self.prev_error = 0.0
        self.integral = 0.0
        self.last_time = time.time()
        
        # Add fields to track performance
        self.last_output = 0.0
        self.max_integral = 0.0
        self.max_error = 0.0
        self.total_error_squared = 0.0
        self.sample_count = 0
        self.last_setpoint = 0.0
        self.last_measured = 0.0
        
    def compute(self, setpoint: float, measured_value: float) -> float:
        """Calculate PID output value for given reference input and feedback"""
        current_time = time.time()
        dt = current_time - self.last_time
        
        # Guard against division by zero or very small dt
        if dt < 0.001:
            dt = 0.001
            
        # Calculate error
        error = setpoint - measured_value
        
        # Track max error
        if abs(error) > abs(self.max_error):
            self.max_error = error
            
        # Calculate integral with anti-windup
        self.integral += error * dt
        self.integral = max(-1.0, min(1.0, self.integral))  # Limit integral term
        
        # Track max integral
        if abs(self.integral) > abs(self.max_integral):
            self.max_integral = self.integral
        
        # Calculate derivative (with filter for noise reduction)
        derivative = (error - self.prev_error) / dt
        
        # Calculate output
        output = (self.kp * error) + (self.ki * self.integral) + (self.kd * derivative)
        
        # Limit output to -1.0 to 1.0
        output = max(-1.0, min(1.0, output))
        
        # Save values for next iteration
        self.prev_error = error
        self.last_time = current_time
        self.last_output = output
        self.last_setpoint = setpoint
        self.last_measured = measured_value
        
        # Track statistics for performance analysis
        self.total_error_squared += error * error
        self.sample_count += 1
        
        return output
        
    def get_rms_error(self) -> float:
        """Get root mean square error"""
        if self.sample_count == 0:
            return 0.0
        return math.sqrt(self.total_error_squared / self.sample_count)
        
    def reset(self) -> None:
        """Reset the PID controller"""
        self.prev_error = 0.0
        self.integral = 0.0
        self.last_time = time.time()
        self.max_integral = 0.0
        self.max_error = 0.0
        self.total_error_squared = 0.0
        self.sample_count = 0

class EthernetManager: #TODO multiple socket connections (maybe)
    """Manages all network communications for the ROV"""
    
    def __init__(self, control_ip: str = '192.168.1.237', control_port: int = 4891):
        # Connection parameters
        self.control_ip = control_ip
        self.control_port = control_port
        
        # Control connection
        self.control_socket = None
        self.connected = False
        
        # Communication threads
        self.control_thread = None
        self.running = False
        
        # Callbacks for received data
        self.control_callback = None
        
        # Connection status
        self.last_heartbeat = 0
        
        logger.info(f"Ethernet manager initialized with control IP: {control_ip}:{control_port}")
        
    def start_control_server(self) -> bool:
        """Start the control server to receive commands"""
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.control_socket.bind((self.control_ip, self.control_port))
            self.control_socket.listen(1)
            self.control_socket.settimeout(1.0)  # 1 second timeout for accept()
            
            self.running = True
            self.control_thread = threading.Thread(target=self._control_listener, daemon=True)
            self.control_thread.start()
            
            logger.info(f"Control server started on {self.control_ip}:{self.control_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start control server: {e}")
            return False
    
    def _control_listener(self) -> None:
        """Thread function to listen for control connections"""
        logger.info("Control listener thread started")
        
        while self.running:
            try:
                # Accept new connections
                client_socket, client_address = self.control_socket.accept()
                logger.info(f"Control connection from {client_address}")
                
                self.connected = True
                client_socket.settimeout(0.5)  # 500ms timeout for recv
                
                # Handle this client until disconnection
                while self.running and self.connected:
                    try:
                        data = client_socket.recv(1024)
                        if not data:
                            logger.info("Client disconnected")
                            self.connected = False
                            break
                            
                        # Parse and process data
                        self._process_control_data(data, client_socket)
                        
                    except socket.timeout:
                        # This is expected behavior for the timeout
                        continue
                    except Exception as e:
                        logger.error(f"Error receiving control data: {e}")
                        self.connected = False
                        break
                
                # Close this client connection
                try:
                    client_socket.close()
                except:
                    pass
                    
            except socket.timeout:
                # This is expected behavior for the accept timeout
                continue
            except Exception as e:
                if self.running:  # Only log if we're supposed to be running
                    logger.error(f"Control listener error: {e}")
                time.sleep(1)  # Prevent tight loop if errors occur
    
    def _process_control_data(self, data: bytes, client_socket: socket.socket) -> None:
        """Process received control data"""
        try:
            # Update last heartbeat time
            self.last_heartbeat = time.time()
            
            # Decode and parse data
            raw_data = data.decode('utf-8')
            logger.debug(f"Received control data: {raw_data}")
            
            # Convert single quotes to double quotes for valid JSON
            json_str = raw_data.replace("'", '"')
            control_data = json.loads(json_str)
            
            # Call the callback if registered
            if self.control_callback:
                self.control_callback(control_data)
            
            # Send acknowledgment
            client_socket.send("ACK".encode('utf-8'))
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decoding error: {e}")
            logger.error(f"Raw data: {raw_data}")
        except Exception as e:
            logger.error(f"Control data processing error: {e}")
    
    def set_control_callback(self, callback) -> None:
        """Set the callback for received control data"""
        self.control_callback = callback
    
    def send_telemetry(self, telemetry_data: Dict) -> bool:
        """Send telemetry data back to the control station"""
        # This would be implemented to send sensor and status data back
        # through another socket or the existing control socket
        logger.debug(f"Would send telemetry: {telemetry_data}")
        return True
    
    def shutdown(self) -> None:
        """Clean shutdown of all network connections"""
        logger.info("Shutting down Ethernet manager")
        self.running = False
        
        # Close control socket
        if self.control_socket:
            try:
                self.control_socket.close()
            except:
                pass
            
        # Wait for threads to terminate
        if self.control_thread and self.control_thread.is_alive():
            self.control_thread.join(timeout=1.0)
            
        logger.info("Ethernet manager shutdown complete")

class PIDSystem:
    """Manages thruster control using PID feedback for stability"""
    
    def __init__(self, pca: PCA9685):
        self.pca = pca
        
        # Initialize thrusters with their channel assignments
        # Channel map for the thrusters
        self.thruster_channels = [0, 7, 2, 5, 1, 4, 6, 3]
        self.thruster_names = [
            "FrontLeft", "FrontLeftUp", "BackLeft", "BackLeftUp",
            "FrontRightUp", "BackRight", "BackRightUp", "FrontRight"
        ]
        
        # Create thruster objects
        self.thrusters = []
        for i, channel in enumerate(self.thruster_channels):
            name = self.thruster_names[i] if i < len(self.thruster_names) else f"Thruster{i}"
            self.thrusters.append(Thruster(channel, pca, name=name))
        
        # Initialize PID controllers for each axis
        self.pid_roll = PIDController(kp=0.2, ki=0.05, kd=0.1)
        self.pid_pitch = PIDController(kp=0.2, ki=0.05, kd=0.1)
        self.pid_yaw = PIDController(kp=0.2, ki=0.0, kd=0.1)
        self.pid_depth = PIDController(kp=0.3, ki=0.1, kd=0.1)
        
        # Current commanded values
        self.target_speeds = [0.0] * len(self.thrusters)
        
        # Stabilization
        self.stabilize_enabled = True
        self.target_roll = 0.0
        self.target_pitch = 0.0
        self.target_yaw = 0.0
        self.target_depth = 0.0
        
        logger.info("PID System initialized")
    
    def initialize(self) -> None:
        """Initialize all thrusters"""
        logger.info("Initializing all thrusters...")
        for thruster in self.thrusters:
            thruster.initialize()
        logger.info("Thruster initialization complete")
    
    def set_manual_speeds(self, speeds: List[float]) -> None:
        """Set thruster speeds directly (bypassing PID)"""
        if len(speeds) != len(self.thrusters):
            logger.error(f"Expected {len(self.thrusters)} speeds, got {len(speeds)}")
            return
            
        self.target_speeds = speeds
        self._update_thrusters()
        logger.debug(f"Manual speeds set: {speeds}")
    
    def set_movement(self, forward: float, strafe: float, yaw: float, vertical: float) -> None:
        """
        Set movement using high-level controls
        All values should be in range -1.0 to 1.0
        """
        # Implement thruster mixing for combined movement
        # This is a simple implementation that would need to be tuned
        
        # Limit all inputs to -1.0 to 1.0
        forward = max(-1.0, min(1.0, forward))
        strafe = max(-1.0, min(1.0, strafe))
        yaw = max(-1.0, min(1.0, yaw))
        vertical = max(-1.0, min(1.0, vertical))
        
        # Calculate horizontal thruster values (simplified)
        front_left = forward + strafe - yaw
        front_right = forward - strafe + yaw
        back_left = forward - strafe - yaw
        back_right = forward + strafe + yaw
        
        # Normalize to ensure we don't exceed -1.0 to 1.0
        max_horizontal = max(abs(front_left), abs(front_right), abs(back_left), abs(back_right), 1.0)
        front_left /= max_horizontal
        front_right /= max_horizontal
        back_left /= max_horizontal
        back_right /= max_horizontal
        
        # Set vertical thrusters (all at same speed for now)
        front_left_up = vertical
        front_right_up = vertical
        back_left_up = vertical
        back_right_up = vertical
        
        # Apply to thrusters in the correct order to match self.thruster_channels
        # Order: [FrontLeft, FrontLeftUp, BackLeft, BackLeftUp, FrontRightUp, BackRight, BackRightUp, FrontRight]
        self.target_speeds = [
            front_left, front_left_up, back_left, back_left_up,
            front_right_up, back_right, back_right_up, front_right
        ]
        
        self._update_thrusters()
        logger.debug(f"Movement set: fwd={forward:.2f}, strafe={strafe:.2f}, yaw={yaw:.2f}, vert={vertical:.2f}")
    
    def _update_thrusters(self) -> None:
        """Update all thrusters with current speeds"""
        changes_made = False
        
        for i, speed in enumerate(self.target_speeds):
            if i < len(self.thrusters):
                old_speed = self.thrusters[i].current_speed
                if abs(old_speed - speed) > 0.05:  # Only track significant changes
                    changes_made = True
                    logger.debug(f"Thruster {self.thrusters[i].name}: {old_speed:.2f} → {speed:.2f}")
                self.thrusters[i].set_speed(speed)
        
        if changes_made:
            # Log a summary of current thruster configuration for debugging
            horizontal = [self.target_speeds[0], self.target_speeds[7], self.target_speeds[2], self.target_speeds[5]]
            vertical = [self.target_speeds[1], self.target_speeds[4], self.target_speeds[3], self.target_speeds[6]]
            
            # Calculate average thrusts by direction
            fwd_thrust = (self.target_speeds[0] + self.target_speeds[7] + 
                          self.target_speeds[2] + self.target_speeds[5]) / 4
            vert_thrust = (self.target_speeds[1] + self.target_speeds[4] + 
                           self.target_speeds[3] + self.target_speeds[6]) / 4
            
            logger.info(f"Thruster configuration updated - Forward: {fwd_thrust:.2f}, "
                       f"Vertical: {vert_thrust:.2f}, "
                       f"Max Horizontal: {max(abs(h) for h in horizontal):.2f}, "
                       f"Max Vertical: {max(abs(v) for v in vertical):.2f}")
    
    def stop_all(self) -> None:
        """Emergency stop all thrusters"""
        logger.info("Emergency stop - all thrusters")
        for thruster in self.thrusters:
            thruster.stop()
        self.target_speeds = [0.0] * len(self.thrusters)
    
    def process_sensor_data(self, roll: float, pitch: float, yaw: float, depth: float) -> None:
        """
        Process sensor data for PID-based stabilization
        This would be called frequently with updated sensor values
        """
        if not self.stabilize_enabled:
            return
            
        # Record original values before PID adjustment
        original_speeds = self.target_speeds.copy()
            
        # Calculate PID outputs for each axis
        roll_correction = self.pid_roll.compute(self.target_roll, roll)
        pitch_correction = self.pid_pitch.compute(self.target_pitch, pitch)
        yaw_correction = self.pid_yaw.compute(self.target_yaw, yaw)
        depth_correction = self.pid_depth.compute(self.target_depth, depth)
        
        # Only log if corrections are significant
        has_significant_correction = (
            abs(roll_correction) > 0.05 or 
            abs(pitch_correction) > 0.05 or 
            abs(yaw_correction) > 0.05 or 
            abs(depth_correction) > 0.05
        )
        
        if has_significant_correction:
            logger.info(f"IMU-DRIVEN PID CORRECTION - Roll: {roll:.1f}° → {self.target_roll:.1f}° (corr: {roll_correction:.3f}), "
                       f"Pitch: {pitch:.1f}° → {self.target_pitch:.1f}° (corr: {pitch_correction:.3f}), "
                       f"Yaw: {yaw:.1f}° → {self.target_yaw:.1f}° (corr: {yaw_correction:.3f}), "
                       f"Depth: {depth:.2f}m → {self.target_depth:.2f}m (corr: {depth_correction:.3f})")
        else:
            # Debug level for small adjustments
            logger.debug(f"PID minor adjust - Roll err: {self.target_roll-roll:.2f}°, "
                        f"Pitch err: {self.target_pitch-pitch:.2f}°, "
                        f"Yaw err: {self.target_yaw-yaw:.2f}°, "
                        f"Depth err: {self.target_depth-depth:.2f}m")
        
        # Apply corrections to thruster speeds
        # Apply roll correction to vertical thrusters
        self.target_speeds[1] += roll_correction  # FrontLeftUp
        self.target_speeds[4] -= roll_correction  # FrontRightUp
        self.target_speeds[3] += roll_correction  # BackLeftUp
        self.target_speeds[6] -= roll_correction  # BackRightUp
        
        # Apply pitch correction to vertical thrusters
        self.target_speeds[1] += pitch_correction  # FrontLeftUp
        self.target_speeds[4] += pitch_correction  # FrontRightUp
        self.target_speeds[3] -= pitch_correction  # BackLeftUp
        self.target_speeds[6] -= pitch_correction  # BackRightUp
        
        # Apply yaw correction to horizontal thrusters
        self.target_speeds[0] -= yaw_correction  # FrontLeft
        self.target_speeds[7] += yaw_correction  # FrontRight
        self.target_speeds[2] -= yaw_correction  # BackLeft
        self.target_speeds[5] += yaw_correction  # BackRight
        
        # Apply depth correction to all vertical thrusters
        for i in [1, 3, 4, 6]:  # All vertical thruster indices
            self.target_speeds[i] += depth_correction
        
        # Ensure all speeds are within -1.0 to 1.0
        self.target_speeds = [max(-1.0, min(1.0, speed)) for speed in self.target_speeds]
        
        # Log significant thruster changes caused by PID
        thruster_changes = []
        for i, (before, after) in enumerate(zip(original_speeds, self.target_speeds)):
            if abs(after - before) > 0.05:  # Only log meaningful changes
                thruster_name = self.thruster_names[i] if i < len(self.thruster_names) else f"Thruster{i}"
                thruster_changes.append(f"{thruster_name}: {before:.2f} → {after:.2f}")
        
        if thruster_changes:
            logger.info(f"PID THRUSTER ADJUSTMENTS - " + ", ".join(thruster_changes))
        
        # Update thrusters with new speeds
        self._update_thrusters()
    
    def enable_stabilization(self, enable: bool = True) -> None:
        """Enable or disable automatic stabilization"""
        # Only log if there's a change in state
        if self.stabilize_enabled != enable:
            self.stabilize_enabled = enable
            if enable:
                # Reset PID controllers when enabling stabilization
                self.pid_roll.reset()
                self.pid_pitch.reset()
                self.pid_yaw.reset()
                self.pid_depth.reset()
                logger.info("PID stabilization enabled with parameters:")
                logger.info(f"  Roll:  Kp={self.pid_roll.kp:.2f}, Ki={self.pid_roll.ki:.2f}, Kd={self.pid_roll.kd:.2f}")
                logger.info(f"  Pitch: Kp={self.pid_pitch.kp:.2f}, Ki={self.pid_pitch.ki:.2f}, Kd={self.pid_pitch.kd:.2f}")
                logger.info(f"  Yaw:   Kp={self.pid_yaw.kp:.2f}, Ki={self.pid_yaw.ki:.2f}, Kd={self.pid_yaw.kd:.2f}")
                logger.info(f"  Depth: Kp={self.pid_depth.kp:.2f}, Ki={self.pid_depth.ki:.2f}, Kd={self.pid_depth.kd:.2f}")
                logger.info(f"  Targets: Roll={self.target_roll:.1f}°, Pitch={self.target_pitch:.1f}°, "
                           f"Yaw={self.target_yaw:.1f}°, Depth={self.target_depth:.2f}m")
            else:
                # Log PID integral terms to help with tuning
                logger.info("PID stabilization disabled. Final integral terms:")
                logger.info(f"  Roll={self.pid_roll.integral:.3f}, Pitch={self.pid_pitch.integral:.3f}, "
                           f"Yaw={self.pid_yaw.integral:.3f}, Depth={self.pid_depth.integral:.3f}")
    
    def set_targets(self, roll: float = 0.0, pitch: float = 0.0, yaw: float = None, depth: float = None) -> None:
        """Set target values for stabilization"""
        self.target_roll = roll
        self.target_pitch = pitch
        
        # Only update yaw if provided (often we want to maintain current heading)
        if yaw is not None:
            self.target_yaw = yaw
            
        # Only update depth if provided
        if depth is not None:
            self.target_depth = depth
            
        logger.info(f"Set targets: roll={roll:.1f}°, pitch={pitch:.1f}°, " + 
                   f"yaw={self.target_yaw:.1f}°, depth={self.target_depth:.2f}m")
    
    def shutdown(self) -> None:
        """Safely shutdown the PID system"""
        logger.info("PID System shutting down")
        self.stop_all()
        logger.info("PID System shutdown complete")
    
    def get_telemetry(self) -> Dict:
        """Get telemetry data for all thrusters"""
        thruster_data = []
        for i, thruster in enumerate(self.thrusters):
            thruster_data.append({
                "name": thruster.name,
                "channel": thruster.channel, 
                "speed": thruster.current_speed,
                "pulse": thruster.current_pulse,
                "active_time": thruster.total_active_time,
                "direction_changes": thruster.direction_changes
            })
        
        return {
            "thrusters": thruster_data,
            "stabilization_enabled": self.stabilize_enabled,
            "targets": {
                "roll": self.target_roll,
                "pitch": self.target_pitch,
                "yaw": self.target_yaw,
                "depth": self.target_depth
            }
        }

class Sensor:
    """Manages all sensor systems for the ROV"""
    
    def __init__(self):
        logger.info("Initializing sensor systems...")
        
        # Initialize IMU sensors
        self.imu = IMUManager(bus_number=7)
        
        # Initialize depth sensor
        self.depth_sensor = DepthSensor()
        
        # Current sensor values (cached for quick access)
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.depth = 0.0
        self.temperature = 20.0
        self.voltage = 12.0
        self.current = 0.0
        
        # Sensor update thread
        self.running = False
        self.sensor_thread = None
        
        # Add logging for sensor data
        self.last_log_time = time.time()
        self.log_interval = 1.0  # Log sensor data every 1 second
        
        logger.info("Sensor systems initialized")
    
    def start(self) -> None:
        """Start sensor data acquisition"""
        self.running = True
        self.sensor_thread = threading.Thread(target=self._sensor_loop, daemon=True)
        self.sensor_thread.start()
        logger.info("Sensor data acquisition started")
    
    def _sensor_loop(self) -> None:
        """Continuously update sensor values"""
        prev_roll, prev_pitch, prev_yaw = 0.0, 0.0, 0.0
        prev_depth = 0.0
        
        while self.running:
            try:
                # Read orientation from IMU
                heading, roll, pitch = self.imu.get_orientation()
                
                # Calculate changes from previous readings
                roll_change = abs(roll - prev_roll)
                pitch_change = abs(pitch - prev_pitch)
                yaw_change = abs(heading - prev_yaw)
                
                # Log significant orientation changes
                if roll_change > 2.0 or pitch_change > 2.0 or yaw_change > 5.0:
                    logger.info(f"IMU MOTION DETECTED - Roll: {prev_roll:.1f}° → {roll:.1f}° (Δ{roll-prev_roll:+.1f}°), "
                               f"Pitch: {prev_pitch:.1f}° → {pitch:.1f}° (Δ{pitch-prev_pitch:+.1f}°), "
                               f"Yaw: {prev_yaw:.1f}° → {heading:.1f}° (Δ{heading-prev_yaw:+.1f}°)")
                
                # Store current values for next comparison
                prev_roll, prev_pitch, prev_yaw = roll, pitch, heading
                
                # Update our cached sensor values
                self.yaw = heading
                self.roll = roll
                self.pitch = pitch
                
                # Read depth data
                self.depth = self.depth_sensor.get_depth()
                depth_change = abs(self.depth - prev_depth)
                
                # Log significant depth changes
                if depth_change > 0.1:  # 10cm change
                    logger.info(f"DEPTH CHANGE DETECTED: {prev_depth:.2f}m → {self.depth:.2f}m (Δ{self.depth-prev_depth:+.2f}m)")
                
                prev_depth = self.depth
                self.temperature = self.depth_sensor.get_temperature()
                
                # Read power status (voltage and current)
                self._update_power_status()
                
                # Periodically log all sensor data (lower frequency)
                current_time = time.time()
                if current_time - self.last_log_time >= self.log_interval:
                    self.last_log_time = current_time
                    # Get calibration status
                    cal_status = self.imu.get_calibration_status()
                    
                    logger.debug(f"Current orientation: Roll={self.roll:.1f}°, Pitch={self.pitch:.1f}°, "
                               f"Yaw={self.yaw:.1f}°, Depth={self.depth:.2f}m")
                    logger.debug(f"IMU Calibration - Sys:{cal_status['system']}/3, Gyro:{cal_status['gyro']}/3, "
                               f"Accel:{cal_status['accel']}/3, Mag:{cal_status['mag']}/3")
                
                # Small delay to avoid excessive CPU usage
                time.sleep(0.05)  # 50ms update rate (20Hz)
                
            except Exception as e:
                logger.error(f"Error in sensor loop: {e}")
                time.sleep(0.5)  # Wait longer on error
    
    def _update_power_status(self) -> None:
        """Update power status (voltage and current)"""
        # Simulate power readings
        # TODO: Replace with actual readings from voltage/current sensors
        self.voltage = 12.0 - (random.random() * 0.5)  # 11.5-12.0V
        self.current = 1.0 + (random.random() * 4.0)   # 1-5A
    
    def get_orientation(self) -> Tuple[float, float, float]:
        """Get current roll, pitch, yaw in degrees"""
        return self.roll, self.pitch, self.yaw
    
    def get_depth(self) -> float:
        """Get current depth in meters"""
        return self.depth
    
    def get_temperature(self) -> float:
        """Get water temperature in Celsius"""
        return self.temperature
    
    def get_power_status(self) -> Tuple[float, float]:
        """Get current voltage and current draw"""
        return self.voltage, self.current
    
    def get_telemetry(self) -> Dict:
        """Get all telemetry data as a dictionary"""
        return {
            "orientation": {
                "roll": self.roll,
                "pitch": self.pitch,
                "yaw": self.yaw
            },
            "depth": self.depth,
            "temperature": self.temperature,
            "power": {
                "voltage": self.voltage,
                "current": self.current
            },
            "imu_calibration": self.imu.get_calibration_status(),
            "timestamp": time.time()
        }
    
    def get_calibration_status(self) -> Dict:
        """Get IMU calibration status"""
        return self.imu.get_calibration_status()
    
    def is_fully_calibrated(self) -> bool:
        """Check if IMU is fully calibrated"""
        return self.imu.is_fully_calibrated()
    
    def shutdown(self) -> None:
        """Safely shutdown all sensors"""
        logger.info("Sensor systems shutting down")
        self.running = False
        if self.sensor_thread and self.sensor_thread.is_alive():
            self.sensor_thread.join(timeout=2.0)
        self.imu.close()
        logger.info("Sensor systems shutdown complete")

class Tool:
    """Base class for ROV tools"""
    
    def __init__(self, name: str):
        self.name = name
        logger.info(f"{name} tool initialized")
        
    def activate(self) -> None:
        """Activate the tool"""
        logger.info(f"{self.name} tool activated")
        
    def deactivate(self) -> None:
        """Deactivate the tool"""
        logger.info(f"{self.name} tool deactivated")
        
    def shutdown(self) -> None:
        """Safely shutdown the tool"""
        self.deactivate()
        logger.info(f"{self.name} tool shutdown complete")

class Bucket(Tool):
    """Sampling bucket tool"""
    
    def __init__(self, pca: PCA9685, servo_channel: int = 8):
        super().__init__("Bucket")
        self.servo = Servo(servo_channel, pca, name="Bucket")
        self.open_angle = 0    # Modify to appropriate values
        self.closed_angle = 90  # Modify to appropriate values
        self.current_state = "closed"
        
    def open(self) -> None:
        """Open the bucket"""
        self.servo.set_angle(self.open_angle)
        self.current_state = "open"
        logger.info("Bucket opened")
        
    def close(self) -> None:
        """Close the bucket"""
        self.servo.set_angle(self.closed_angle)
        self.current_state = "closed"
        logger.info("Bucket closed")
        
    def activate(self) -> None:
        """Toggle the bucket state"""
        if self.current_state == "closed":
            self.open()
        else:
            self.close()

class Net(Tool):
    """Sample collection net tool"""
    
    def __init__(self, pca: PCA9685, servo_channel: int = 9):
        super().__init__("Net")
        self.servo = Servo(servo_channel, pca, name="Net")
        self.retracted_angle = 0    # Modify to appropriate values
        self.deployed_angle = 90   # Modify to appropriate values
        self.current_state = "retracted"
        
    def deploy(self) -> None:
        """Deploy the net"""
        self.servo.set_angle(self.deployed_angle)
        self.current_state = "deployed"
        logger.info("Net deployed")
        
    def retract(self) -> None:
        """Retract the net"""
        self.servo.set_angle(self.retracted_angle)
        self.current_state = "retracted"
        logger.info("Net retracted")
        
    def activate(self) -> None:
        """Toggle the net state"""
        if self.current_state == "retracted":
            self.deploy()
        else:
            self.retract()

class Syringe(Tool):
    """Water sampling syringe tool"""
    
    def __init__(self, pca: PCA9685, servo_channel: int = 10):
        super().__init__("Syringe")
        self.servo = Servo(servo_channel, pca, name="Syringe")
        self.empty_angle = 0     # Modify to appropriate values
        self.filled_angle = 90   # Modify to appropriate values
        self.current_state = "empty"
        
    def draw(self) -> None:
        """Draw water into the syringe"""
        self.servo.set_angle(self.filled_angle)
        self.current_state = "filled"
        logger.info("Syringe filled")
        
    def empty(self) -> None:
        """Empty the syringe"""
        self.servo.set_angle(self.empty_angle)
        self.current_state = "empty"
        logger.info("Syringe emptied")
        
    def activate(self) -> None:
        """Toggle the syringe state"""
        if self.current_state == "empty":
            self.draw()
        else:
            self.empty()

class ROV:
    """Main ROV system that manages all components"""
    
    def __init__(self):
        logger.info("Initializing ROV system...")
        

        # Initialize hardware interface
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50  # Standard frequency for servos and ESCs
        
        # Initialize subsystems
        logger.info("Initializing subsystems...")
        
        # Core systems
        self.arm = Arm(self.pca)
        self.pid_system = PIDSystem(self.pca)
        self.ethernet = EthernetManager()
        self.sensors = Sensor()
        
        # Tools
        self.bucket = Bucket(self.pca)
        self.net = Net(self.pca)
        self.syringe = Syringe(self.pca)
        
        # System state
        self.running = False
        self.last_telemetry_time = 0
        self.telemetry_interval = 0.2  # Send telemetry every 200ms
        self.stabilization_enabled = True
        
        # Register callbacks
        self.ethernet.set_control_callback(self._process_control_data)
        
        logger.info("ROV system initialization complete")
    
    def start(self) -> None:
        """Start the ROV system"""
        logger.info("Starting ROV system...")
        
        # Initialize hardware
        self.pid_system.initialize()
        self.arm.initialize()
        
        # Start network services
        self.ethernet.start_control_server()
        
        # Start sensor acquisition
        self.sensors.start()
        
        self.running = True
        logger.info("ROV system started")
        
        # Main loop
        self._main_loop()
    
    def _main_loop(self) -> None:
        """Main control loop"""
        logger.info("Entering main control loop")
        
        while self.running:
            try:
                # Update stabilization if enabled (handles sensor reading + PID)
                if self.stabilization_enabled:
                    self._update_stabilization()
                
                # Send telemetry at specified interval
                current_time = time.time()
                if current_time - self.last_telemetry_time >= self.telemetry_interval:
                    self._send_telemetry()
                    self.last_telemetry_time = current_time
                
                # Small delay to avoid excessive CPU usage
                time.sleep(0.01)  # 10ms loop time (100Hz)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(0.5)  # Wait longer on error
    
    def _send_telemetry(self) -> None:
        """Send telemetry data to control station"""
        telemetry = {
            "sensors": self.sensors.get_telemetry(),
            "arm_state": self.arm.current_state.name,
            "thrusters": self.pid_system.get_telemetry(),
            "tools": {
                "bucket": self.bucket.current_state,
                "net": self.net.current_state,
                "syringe": self.syringe.current_state
            },
            "stabilization": self.stabilization_enabled
        }
        
        self.ethernet.send_telemetry(telemetry)
    
    def _process_control_data(self, control_data: Dict) -> None:
        """Process control data received from the control station"""
        try:
            # Process stabilization commands
            if 'stabilization' in control_data:
                enable = control_data['stabilization'].get('enable', None)
                if enable is not None:
                    self.stabilization_enabled = enable
                    self.pid_system.enable_stabilization(enable)
                    logger.info(f"Stabilization {'enabled' if enable else 'disabled'}")
                
                # Process target values for stabilization
                if 'targets' in control_data['stabilization']:
                    targets = control_data['stabilization']['targets']
                    roll = targets.get('roll', 0.0)
                    pitch = targets.get('pitch', 0.0)
                    yaw = targets.get('yaw', None)
                    depth = targets.get('depth', None)
                    self.pid_system.set_targets(roll, pitch, yaw, depth)
            
            # Process motor commands if present
            if 'motor_values' in control_data:
                motor_values = control_data['motor_values']
                if isinstance(motor_values, list) and len(motor_values) == 8:
                    self.pid_system.set_manual_speeds(motor_values)
                    logger.debug("Updated thruster speeds")
            
            # Process movement commands if present
            if 'movement' in control_data:
                movement = control_data['movement']
                forward = movement.get('forward', 0.0)
                strafe = movement.get('strafe', 0.0)
                yaw = movement.get('yaw', 0.0)
                vertical = movement.get('vertical', 0.0)
                self.pid_system.set_movement(forward, strafe, yaw, vertical)
                logger.debug("Updated movement commands")
            
            # Process arm commands
            if 'buttons' in control_data or 'hats' in control_data:
                buttons = control_data.get('buttons', [])
                prev_buttons = control_data.get('prev_buttons', [0] * len(buttons))
                hats = control_data.get('hats', [(0, 0)])
                prev_hats = control_data.get('prev_hats', hats)
                
                self.arm.process_controller_input(buttons, prev_buttons, hats, prev_hats)
                
                # Also check for tool commands
                if len(buttons) > 7:
                    # Example: button 7 toggles bucket
                    if buttons[7] == 1 and (len(prev_buttons) <= 7 or prev_buttons[7] == 0):
                        self.bucket.activate()
                    
                    # Example: button 8 toggles net
                    if len(buttons) > 8 and buttons[8] == 1 and (len(prev_buttons) <= 8 or prev_buttons[8] == 0):
                        self.net.activate()
                    
                    # Example: button 9 toggles syringe
                    if len(buttons) > 9 and buttons[9] == 1 and (len(prev_buttons) <= 9 or prev_buttons[9] == 0):
                        self.syringe.activate()
                        
        except Exception as e:
            logger.error(f"Error processing control data: {e}")
    
    def shutdown(self) -> None:
        """Safely shutdown the ROV system"""
        logger.info("ROV system shutting down...")
        
        # Stop main loop
        self.running = False
        
        # Disable stabilization and stop all thrusters
        self.pid_system.enable_stabilization(False)
        self.pid_system.stop_all()
        
        # Shutdown all subsystems
        self.arm.shutdown()
        self.sensors.shutdown()
        self.ethernet.shutdown()
        self.bucket.shutdown()
        self.net.shutdown()
        self.syringe.shutdown()
        
        # Close hardware connections
        self.pca.deinit()
        
        logger.info("ROV system shutdown complete")

    def _update_stabilization(self) -> None:
        """
        Update stabilization based on current sensor readings
        This method makes the link between IMU data and PID control explicit
        """
        if self.stabilization_enabled:
            # Get current sensor data
            roll, pitch, yaw = self.sensors.get_orientation()
            depth = self.sensors.get_depth()
            
            # Log the fact that we're using this data for stabilization
            logger.debug(f"Stabilization using sensor data - Roll: {roll:.1f}°, Pitch: {pitch:.1f}°, " 
                        f"Yaw: {yaw:.1f}°, Depth: {depth:.2f}m")
            
            # Process through PID system
            self.pid_system.process_sensor_data(roll, pitch, yaw, depth)

def main():
    """Entry point for the ROV system"""
    # Import needed only in main function
    import argparse
    import random
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='ROV Control System')
    parser.add_argument('--log-level', type=str, default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')
    args = parser.parse_args()
    
    # Set log level
    logging.getLogger().setLevel(args.log_level)
    
    # Create and start the ROV
    rov = ROV()
    try:
        rov.start()
    except KeyboardInterrupt:
        logger.info("ROV system interrupted by user")
        rov.shutdown()
    except Exception as e:
        logger.error(f"Error in ROV system: {e}")
        rov.shutdown()

if __name__ == '__main__':
    main()