from smbus2 import SMBus
import time
import socket
import json
import threading
import logging
from enum import Enum
from time import sleep

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

    def open_claw(self):
        """Open the claw"""
        self.servos["claw"].set_angle(0)  # 0° = open
        print("Claw opened")
        
    def close_claw(self):
        """Close the claw"""
        self.servos["claw"].set_angle(180)  # 180° = closed
        print("Claw closed")
        
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
# --------------------------- Arm ROV Class ---------------------------
class ArmROV:
    def __init__(self):
        logger.info("Initializing Arm ROV...")
        
        # Initialize PCA9685 driver
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50  # Standard frequency for servos
        
        # Create arm
        self.arm = Arm(self.pca)
        
        # Initialize Ethernet Manager for network communication
        self.ethernet = EthernetManager(control_ip='192.168.1.237', control_port=4891)
        self.ethernet.set_control_callback(self.process_command)
        
        self.running = False
        self.last_command_time = time.time()
        
        logger.info("Arm ROV initialization complete")
    
    def start(self):
        """Start the Arm ROV system."""
        logger.info("Starting Arm ROV system...")
        
        # Start the control server
        if not self.ethernet.start_control_server():
            logger.error("Failed to start control server.")
            return False
        
        self.running = True
        self._main_loop()
        return True
    
    def _main_loop(self):
        """Main control loop for the Arm ROV."""
        logger.info("Entering main control loop...")
        
        while self.running:
            try:
                current_time = time.time()
                
                # Check for timeout (lost connection)
                if current_time - self.last_command_time > 30.0:
                    # Move to safe position after timeout
                    logger.warning("Command timeout - moving arm to stowed position")
                    self.arm.set_state(ArmState.STOWED)
                    self.last_command_time = current_time  # Reset timer after stowing
                
                time.sleep(0.01)  # Small delay for loop iteration
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(0.5)
    
    def process_command(self, command_data):
        """Process received command data for arm control."""
        try:
            # Log the raw command data for debugging at trace level only
            logger.debug(f"Received command data: {command_data}")
            
            # Update last command time
            self.last_command_time = time.time()
            
            # Validate the structure of the command data
            if 'controller' not in command_data or not isinstance(command_data['controller'], dict):
                logger.warning("Invalid command data: 'controller' key missing or malformed")
                return False
            
            # Extract the controller data
            controller = command_data['controller']
            
            # Save the current state before processing any new commands
            previous_state = self.arm.current_state
            
            # Track if we've actually processed any commands in this cycle
            command_processed = False
            
            # Process button inputs for arm control - only one command per method call
            if controller.get('a', 0) == 1:
                self.arm.open_claw()
                command_processed = True
            elif controller.get('b', 0) == 1:
                self.arm.close_claw()
                command_processed = True
            elif controller.get('x', 0) == 1 and previous_state != ArmState.STOWED:
                # Only execute stow command if we're not already in STOWED state
                self.arm.set_state(ArmState.STOWED)
                command_processed = True
            elif controller.get('y', 0) == 1 and previous_state != ArmState.FULLY_OUT:
                # Only execute if we're not already in this state
                self.arm.set_state(ArmState.FULLY_OUT)
                command_processed = True
            elif controller.get('lb', 0) == 1 and previous_state != ArmState.OUT_DOWN:
                # Only execute if we're not already in this state
                self.arm.set_state(ArmState.OUT_DOWN)
                command_processed = True
            elif controller.get('rb', 0) == 1 and previous_state != ArmState.FULLY_DOWN:
                # Only execute if we're not already in this state
                self.arm.set_state(ArmState.FULLY_DOWN)
                command_processed = True
            else:
                # Process D-pad (hat) inputs for wrist rotation
                dpad_x = controller.get('dpad_x', 0)
                if dpad_x == -1:  # Left on D-pad
                    self.arm.adjust_wrist(-1)
                    command_processed = True
                elif dpad_x == 1:  # Right on D-pad
                    self.arm.adjust_wrist(1)
                    command_processed = True
            
            # Log success if we actually did something
            if command_processed:
                logger.info("Controller input processed successfully")
            return True
        except Exception as e:
            # Log the error and the raw command data for debugging
            logger.error(f"Error processing command: {e}")
            logger.debug(f"Command data that caused error: {command_data}")
            return False
    
    def shutdown(self):
        """Shutdown the Arm ROV system."""
        logger.info("Shutting down Arm ROV system...")
        self.running = False
        
        # Move arm to stowed position before shutdown
        try:
            self.arm.set_state(ArmState.STOWED)
            time.sleep(1)  # Wait for arm to reach position
        except Exception as e:
            logger.error(f"Error stowing arm during shutdown: {e}")
        
        # Shutdown ethernet
        self.ethernet.shutdown()
        
        # Close PCA9685
        self.pca.deinit()
        
        logger.info("Arm ROV system shutdown complete")

# --------------------------- Main Entry Point ---------------------------
def main():
    """Main function to start the Arm ROV system."""
    arm_rov = ArmROV()
    
    try:
        # Start the ARM ROV
        arm_rov.start()
    except KeyboardInterrupt:
        logger.info("ARM ROV interrupted by user")
    except Exception as e:
        logger.error(f"Error in ARM ROV system: {e}")
    finally:
        # Ensure proper shutdown
        arm_rov.shutdown()

if __name__ == '__main__':
    main()