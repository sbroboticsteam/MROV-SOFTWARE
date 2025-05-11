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

# Add this new class for 360-degree continuous rotation servos
class ContinuousServo(Servo):
    """Class for controlling continuous rotation servos"""
    
    def __init__(self, channel, pca, min_pulse=500, max_pulse=2500, name="unnamed", stop_pulse=1500):
        super().__init__(channel, pca, min_pulse, max_pulse, name)
        self.speed = 0  # Speed from -1 (full reverse) to 1 (full forward), 0 is stopped
        self.stop_pulse = stop_pulse  # Calibrated stop pulse - 1536 based on calibration
        
    def set_speed(self, speed):
        """Set the rotation speed of the servo.
        
        Args:
            speed: Float from -1.0 (full reverse) to 1.0 (full forward), 0 is stopped
        """
        self.speed = max(-1.0, min(1.0, speed))  # Ensure speed is within bounds
        
        # If speed is very close to zero or exactly zero, use the calibrated stop pulse
        if abs(self.speed) < 0.05:
            self._set_pulse_width(self.stop_pulse)
            logger.debug(f"{self.name} (Channel {self.channel}): Speed near zero - using calibrated stop pulse {self.stop_pulse}μs")
        else:
            # For non-zero speeds, use a modified mapping that accounts for the offset
            if self.speed > 0:
                # Map positive speeds from the calibrated stop to max_pulse
                pulse_width = self.stop_pulse + (self.speed * (self.max_pulse - self.stop_pulse))
            else:
                # Map negative speeds from min_pulse to the calibrated stop
                pulse_width = self.stop_pulse + (self.speed * (self.stop_pulse - self.min_pulse))
                
            self._set_pulse_width(pulse_width)
            logger.debug(f"{self.name} (Channel {self.channel}): Speed set to {self.speed:.2f}")
        
    def stop(self):
        """Stop the continuous rotation servo using calibrated stop pulse with smoother transition"""
        # Get current speed before stopping
        prev_speed = self.speed
        
        # For smoother stopping when coming from positive speed (which causes the jump)
        if prev_speed > 0.3:
            # Step down speed gradually if we were moving fast
            intermediate_speed = prev_speed * 0.5
            self._set_pulse_width(self.stop_pulse + (intermediate_speed * (self.max_pulse - self.stop_pulse)))
            time.sleep(0.03)
        
        # Now fully stop
        self.speed = 0
        self._set_pulse_width(self.stop_pulse)
        logger.debug(f"{self.name} (Channel {self.channel}): Stopped at {self.stop_pulse}μs")
        
    def calibrate_stop(self, pulse):
        """Calibrate the stop pulse width for this specific servo"""
        self.stop_pulse = pulse
        logger.info(f"{self.name}: Stop pulse calibrated to {pulse}μs")
        self.stop()  # Apply the new stop pulse

# Then modify the Arm class to use the ContinuousServo for the claw

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
    # Modified to handle continuous rotation claw
    POSITIONS = {
        ArmState.STOWED: {
            "wrist": 0,      # Horizontal rotation
            "elbow": 100,    # Final stowed position for elbow
            "shoulder": 0,   # Final stowed position for shoulder
            "claw_state": "closed"  # Keep claw closed when stowed
        },
        ArmState.FULLY_OUT: {
            "wrist": 90,     # Vertical
            "elbow": 100,    # Down position (~1940μs)
            "shoulder": 150, # Extended out (~1681μs)
            "claw_state": "open"   # Start with claw open when extended
        },
        ArmState.FULLY_DOWN: {
            "wrist": 90,     # Vertical
            "elbow": 160,    # Down position (~1940μs)
            "shoulder": 90,  # Down position (~1186μs)
            "claw_state": "open"   # Start with claw open when down
        },
        ArmState.OUT_DOWN: {
            "wrist": 90,     # Vertical
            "elbow": 160,    # Down position (~1940μs)
            "shoulder": 150, # Extended out (~1681μs)
            "claw_state": "open"   # Start with claw open in this position
        }
    }
    
    def __init__(self, pca):
        """Initialize the arm with all servos"""
        self.pca = pca
        self.current_state = None
        
        # Create servo objects with correct channel assignments and names
        self.servos = {
            "wrist": Servo(2, pca, min_pulse=900, max_pulse=2000, name="Wrist"),
            "elbow": Servo(0, pca, min_pulse=900, max_pulse=2100, name="Elbow"),
            "shoulder": Servo(1, pca, min_pulse=900, max_pulse=2100, name="Shoulder")
        }
        
        # Create continuous rotation servo for claw
        self.claw = ContinuousServo(3, pca, min_pulse=500, max_pulse=2500, name="Claw", stop_pulse=1536)
        
        # Store the current wrist angle for rotation control
        self.current_wrist_angle = 90  # Start at neutral/vertical
        self.current_claw_speed = 0    # Start stopped
        
        # Initialize to the specified position
        self.set_state(ArmState.FULLY_OUT)
        
    def set_state(self, state):
        """Set the arm to a predefined state"""
        if state not in ArmState:
            logger.error(f"Invalid state: {state}")
            return False
            
        logger.info(f"Setting arm to {state.name} position...")
        
        # Special handling for stowed position
        if state == ArmState.STOWED:
            # For stowed position, close claw first for safety
            logger.info("Closing claw for stowed position...")
            self.close_claw()
            time.sleep(0.5)  # Give it time to close
            self.stop_claw()  # Then stop the servo
            time.sleep(0.1)
            
            self._set_stowed_position()
        else:
            # Get the preset positions for this state
            positions = self.POSITIONS[state]
            
            # First handle claw position if specified
            if "claw_state" in positions:
                if positions["claw_state"] == "open":
                    logger.info("Setting claw to open position...")
                    self.open_claw()
                    time.sleep(0.5)  # Give it time to open
                    self.stop_claw()
                elif positions["claw_state"] == "closed":
                    logger.info("Setting claw to closed position...")
                    self.close_claw()
                    time.sleep(0.5)  # Give it time to close
                    self.stop_claw()
            
            # Set each servo to its position with a small delay between each
            for servo_name, angle in positions.items():
                # Skip claw_state as it's not a servo position
                if servo_name == "claw_state":
                    continue
                    
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
        
        # First close claw for safety during stowing
        logger.info("Step 1: Closing claw for stowed position")
        self.close_claw()
        time.sleep(0.5)  # Give it time to close
        self.stop_claw()
        time.sleep(0.1)
        
        # Now set wrist
        logger.info("Step 2: Setting wrist position")
        self.servos["wrist"].set_angle(self.POSITIONS[ArmState.STOWED]["wrist"])
        self.current_wrist_angle = self.POSITIONS[ArmState.STOWED]["wrist"]
        time.sleep(0.3)  # Wait for these servos to move
        
        logger.info("Step 3: Retracting shoulder")
        self.servos["shoulder"].set_angle(0)  # Move shoulder in (~950μs)
        time.sleep(0.8)
        
        logger.info("Step 4: Setting final elbow position")
        self.servos["elbow"].set_angle(100)  # Move elbow to final position
        time.sleep(0.5)
        
        logger.info("Arm stow sequence completed successfully")

    def open_claw(self):
        """Open the claw (rotate in opening direction)"""
        self.claw.set_speed(0.5)  # Adjust speed as needed for your servo
        logger.info("Claw opening")
        
    def close_claw(self):
        """Close the claw (rotate in closing direction)"""
        self.claw.set_speed(-0.5)  # Negative for opposite direction
        logger.info("Claw closing")
        
    def stop_claw(self):
        """Stop claw rotation"""
        self.claw.stop()
        logger.info("Claw stopped")

    def adjust_claw(self, direction, step=0.18):
        """Adjust claw rotation speed
        
        Args:
            direction: -1 for closing, 1 for opening
            step: Speed increment (0.1 = 10% speed change)
        """
        # For continuous servo, we change speed not position
        new_speed = direction * step
        
        if direction > 0:
            # Add smoother transition for opening (which causes the jump)
            self.claw.set_speed(new_speed)
            # Brief delay to let servo stabilize
            time.sleep(0.01)
        else:
            # Regular speed setting for closing
            self.claw.set_speed(new_speed)
        logger.info(f"Claw rotating at speed {new_speed:.2f}")
        
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
            logger.info(f"Wrist rotated to {new_angle}°")