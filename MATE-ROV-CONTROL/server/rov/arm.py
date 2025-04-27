# arm.py
from enum import Enum
import time
import logging
from hardware.servo import Servo

logger = logging.getLogger("Arm")

class ArmState(Enum):
    STOWED = 0
    FULLY_OUT = 1
    FULLY_DOWN = 2
    OUT_DOWN = 3

class Arm:
    """Robotic arm with four servos: claw, wrist, elbow, and shoulder"""
    POSITIONS = {
        ArmState.STOWED: {
            "claw": 180,
            "wrist": 0,
            "elbow": 10,
            "shoulder": 10
        },
        ArmState.FULLY_OUT: {
            "claw": 0,
            "wrist": 90,
            "elbow": 80,
            "shoulder": 140
        },
        ArmState.FULLY_DOWN: {
            "claw": 0,
            "wrist": 90,
            "elbow": 140,
            "shoulder": 80
        },
        ArmState.OUT_DOWN: {
            "claw": 0,
            "wrist": 90,
            "elbow": 140,
            "shoulder": 140
        }
    }
    
    def __init__(self, pca):
        self.pca = pca
        self.current_state = ArmState.STOWED
        self.servos = {
            "claw": Servo(0, pca, min_pulse=500, max_pulse=2100, name="Claw"),
            "wrist": Servo(1, pca, min_pulse=900, max_pulse=2000, name="Wrist"),
            "elbow": Servo(2, pca, min_pulse=850, max_pulse=1600, name="Elbow"),
            "shoulder": Servo(3, pca, min_pulse=900, max_pulse=1600, name="Shoulder")
        }
        self.current_wrist_angle = 90
        logger.info("Arm component initialized")
        
    def initialize(self) -> None:
        logger.info("Initializing arm to stowed position...")
        self.set_state(ArmState.STOWED)
        logger.info("Arm initialization complete")
        
    def set_state(self, state: ArmState) -> bool:
        if state not in ArmState:
            logger.error(f"Invalid arm state: {state}")
            return False
            
        logger.info(f"Setting arm to {state.name} position...")
        positions = self.POSITIONS[state]
        for servo_name, angle in positions.items():
            if servo_name == "wrist" and abs(self.current_wrist_angle - angle) < 5:
                continue
            self.servos[servo_name].set_angle(angle)
            if servo_name == "wrist":
                self.current_wrist_angle = angle
            time.sleep(0.1)
        self.current_state = state
        logger.info(f"Arm now in {state.name} position")
        return True
        
    def open_claw(self) -> None:
        self.servos["claw"].set_angle(0)
        logger.info("Claw opened")
        
    def close_claw(self) -> None:
        self.servos["claw"].set_angle(180)
        logger.info("Claw closed")
        
    def adjust_wrist(self, direction: int, step: int = 5) -> None:
        new_angle = self.current_wrist_angle + (direction * step)
        new_angle = max(0, min(180, new_angle))
        if new_angle != self.current_wrist_angle:
            self.servos["wrist"].set_angle(new_angle)
            self.current_wrist_angle = new_angle
            logger.info(f"Wrist rotated to {new_angle}°")
    
    def process_controller_input(self, buttons: list, prev_buttons: list, hat: list, prev_hat: list) -> None:
        if not buttons or len(buttons) < 12:
            return
        if buttons[0] == 1:
            self.open_claw()
        if buttons[1] == 1:
            self.close_claw()
        if buttons[2] != prev_buttons[2] and buttons[2] == 1:
            self.set_state(ArmState.STOWED)
        if buttons[3] != prev_buttons[3] and buttons[3] == 1:
            self.set_state(ArmState.FULLY_OUT)
        if len(buttons) > 5 and buttons[5] != prev_buttons[5] and buttons[5] == 1:
            self.set_state(ArmState.FULLY_DOWN)
        if len(buttons) > 4 and buttons[4] != prev_buttons[4] and buttons[4] == 1:
            self.set_state(ArmState.OUT_DOWN)
        if hat and len(hat) > 0:
            if hat[0][0] == -1:
                self.adjust_wrist(-1)
            elif hat[0][0] == 1:
                self.adjust_wrist(1)
                
    def shutdown(self) -> None:
        logger.info("Arm shutting down - stowing...")
        self.set_state(ArmState.STOWED)
        logger.info("Arm stowed")
