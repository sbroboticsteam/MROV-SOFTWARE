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
                     
    def _set_pulse_width(self, pulse_width):
        """Set the servo pulse width directly"""
        pw = max(self.min_pulse, min(self.max_pulse, pulse_width))
        
        dc = int((pw / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = dc
        logger.debug(f"{self.name} ch{self.channel}: {pw}µs → dc={dc}")
        self.current_pulse = pw
        time.sleep(0.001) # Small delay to help register changes
        
    def move_smoothly(self, target_pulse, steps=20, delay=0.03):
        """Move the servo gradually to a target position
        
        Args:
            target_pulse: Target pulse width in microseconds
            steps: Number of steps to take (higher = smoother but slower)
            delay: Delay between steps in seconds
        """
        target_pulse = max(self.min_pulse, min(self.max_pulse, target_pulse))
        
        # If we're already at or very close to target, do nothing
        if abs(self.current_pulse - target_pulse) < 10:
            return
            
        start_pulse = self.current_pulse
        pulse_diff = target_pulse - start_pulse
        step_size = pulse_diff / steps
        
        logger.debug(f"{self.name}: Moving smoothly from {start_pulse}µs to {target_pulse}µs in {steps} steps")
        
        # Move in small steps
        for i in range(1, steps + 1):
            next_pulse = int(start_pulse + (step_size * i))
            self._set_pulse_width(next_pulse)
            time.sleep(delay)  # Delay between movements
        

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
            "wrist": 900,     # Vertical
            "elbow": 1900,    # Down position (~1940μs)
            "shoulder": 1620, # Extended out (~1681μs)
            "claw": 1300   # Start with claw open when extended
        },
        ArmState.FULLY_OUT: {
            "elbow": 1460,    # Down position (~1940μs)
            "shoulder": 1425, # Extended out (~1681μs)
        },
        # ArmState.FULLY_DOWN: {
        #     "wrist": 0,     # Vertical
        #     "elbow": 0,    # Down position (~1500μs)
        #     "shoulder": 0,  # Down position (~1186μs)
        #     # "claw_state": "open"   # Start with claw open when down
        # },
        ArmState.OUT_DOWN: {
            "elbow": 1900,    # Down position (~1940μs)
            "shoulder": 1425, # Extended out (~1681μs)
            # "claw_state": "open"   # Start with claw open in this position
        }
    }
    
    def __init__(self, pca):
        """Initialize the arm with all servos"""
        self.pca = pca
        self.current_state = None
        
        # Create servo objects with correct channel assignments and names
        self.servos = {
            "wrist": Servo(5, pca, min_pulse=900, max_pulse=1800, name="Wrist"),
            "elbow": Servo(2, pca, min_pulse=900, max_pulse=2100, name="Elbow"),
            "shoulder": Servo(4, pca, min_pulse=900, max_pulse=2100, name="Shoulder"),
            "claw": Servo(3, pca, min_pulse=1100, max_pulse=2050, name="Claw")
        }
        
        # # Create continuous rotation servo for claw
        # self.claw = ContinuousServo(1, pca, min_pulse=500, max_pulse=2500, name="Claw", stop_pulse=1536)
        
        # Store the current wrist angle for rotation control
        self.current_wrist_pulse = 1500  # Start at neutral/vertical
        
        # Initialize to the specified position
        self.set_state(ArmState.FULLY_OUT)
        
    def set_state(self, state):
        """Set the arm to a predefined state"""
        if state not in ArmState:
            logger.error(f"Invalid state: {state}")
            return False
            
        logger.info(f"Setting arm to {state.name} position...")
        
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
        
        # Set each servo to its position with smooth movement
        # Move larger joints first (shoulder, then elbow, then wrist)
        servo_order = ["shoulder", "elbow", "wrist", "claw"]
        
        for servo_name in servo_order:
            if servo_name in positions:
                pulse = positions[servo_name]
                
                # Skip wrist adjustment if already at target pulse
                if servo_name == "wrist" and abs(self.current_wrist_pulse - pulse) < 50:
                    continue
                    
                # Use smooth movement
                logger.info(f"Moving {servo_name} smoothly to {pulse}µs")
                self.servos[servo_name].move_smoothly(pulse, steps=30, delay=0.02)
                
                # Update current wrist pulse if we're adjusting it
                if servo_name == "wrist":
                    self.current_wrist_pulse = pulse
        
        self.current_state = state
        logger.info(f"Arm now in {state.name} position")
        return True
    # def _set_stowed_position(self):
    #     """Special method to handle the stowing process in correct sequence"""
    #     logger.info("Beginning arm stow sequence...")
        
    #     if(self.current_state == ArmState.STOWED): 
    #         logger.info("Arm already in stowed position, no action taken")
    #         return
        
    #     # First close claw for safety during stowing
    #     logger.info("Step 1: Closing claw for stowed position")
    #     self.close_claw()
    #     time.sleep(0.5)  # Give it time to close
    #     self.stop_claw()
    #     time.sleep(0.1)
        
    #     # Now set wrist
    #     logger.info("Step 2: Setting wrist position")
    #     self.servos["wrist"].set_angle(self.POSITIONS[ArmState.STOWED]["wrist"])
    #     self.current_wrist_angle = self.POSITIONS[ArmState.STOWED]["wrist"]
    #     time.sleep(0.3)  # Wait for these servos to move
        
    #     logger.info("Step 3: Retracting shoulder")
    #     self.servos["shoulder"].set_angle(0)  # Move shoulder in (~950μs)
    #     time.sleep(0.8)
        
    #     logger.info("Step 4: Setting final elbow position")
    #     self.servos["elbow"].set_angle(100)  # Move elbow to final position
    #     time.sleep(0.5)
        
    #     logger.info("Arm stow sequence completed successfully")

    def open_claw(self):
        """Open the claw (rotate in opening direction) smoothly"""
        self.servos["claw"].move_smoothly(1850, steps=20, delay=0.03)  
        logger.info("Claw opening smoothly")
        
    def close_claw(self):
        """Close the claw (rotate in closing direction) smoothly"""
        self.servos["claw"].move_smoothly(1200, steps=20, delay=0.03)
        logger.info("Claw closing smoothly")
    
    # ++++++++++++++++++++++++++++++++
    def stop_claw(self):
        """Stop claw movement"""
        # Use neutral pulse width to stop movement
        self.servos["claw"].move_smoothly(1500, steps=20, delay=0.03)
        logger.info("Claw stopped")
    # +++++++++++++++++++++++++++++++++
    

    def adjust_claw(self, direction, step=0.18):
        """
        Adjust wrist rotation using continuous rotation approach
        direction: -1 for left, 1 for right
        step: speed factor (0-1.0)
        """
        # For continuous-like control, set speed based on direction
        new_speed = direction * step
        
        # Get reference to wrist servo
        wrist_servo = self.servos.get("claw")
        if wrist_servo:
            # Get current pulse or use neutral
            current_pulse = getattr(wrist_servo, 'current_pulse', 1500)
            
            # Calculate new pulse width (pulse increases with positive speed)
            # Each 50μs step is approximately 5 degrees of movement
            new_pulse = current_pulse + (direction * 50)  
            new_pulse = max(1100, min(2050, new_pulse))  # Limit range
            
            # Apply the pulse width directly
            wrist_servo._set_pulse_width(new_pulse)
            logger.info(f"Wrist adjusted to {new_pulse}μs")
        
    def adjust_wrist(self, direction, step=0.18):
        """
        Adjust wrist rotation using continuous rotation approach
        direction: -1 for left, 1 for right
        step: speed factor (0-1.0)
        """
        # Get reference to wrist servo
        wrist_servo = self.servos.get("wrist")
        if wrist_servo:
            # Get current pulse or use neutral
            current_pulse = getattr(wrist_servo, 'current_pulse', 1500)
            
            # Calculate new pulse width (pulse increases with positive speed)
            # Each 50μs step is approximately 5 degrees of movement
            new_pulse = current_pulse + (direction * 50)  
            new_pulse = max(900, min(1800, new_pulse))  # Limit range
            
            # Apply the pulse width directly, with fewer steps for manual control
            wrist_servo.move_smoothly(new_pulse, steps=5, delay=0.01)
            logger.info(f"Wrist adjusted to {new_pulse}μs")
            
            # Update the current wrist pulse
            self.current_wrist_pulse = new_pulse