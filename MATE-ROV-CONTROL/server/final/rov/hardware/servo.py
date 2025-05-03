# hardware/servo.py
from hardware.pca9685 import PCA9685
import time
import logging
from typing import Optional
from enum import Enum
from hardware.pca9685 import PCA9685Channel

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

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
