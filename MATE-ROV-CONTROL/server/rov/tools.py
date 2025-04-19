# tools.py
import logging
from hardware.servo import Servo
from hardware.pca9685 import PCA9685
from time import sleep

logger = logging.getLogger("Tool")

class Tool:
    """Base class for ROV tools"""
    def __init__(self, name: str):
        self.name = name
        logger.info(f"{name} tool initialized")
        
    def activate(self) -> None:
        logger.info(f"{self.name} tool activated")
        
    def deactivate(self) -> None:
        logger.info(f"{self.name} tool deactivated")
        
    def shutdown(self) -> None:
        self.deactivate()
        logger.info(f"{self.name} tool shutdown complete")

class Bucket(Tool):
    """Sampling bucket tool"""
    def __init__(self, pca: PCA9685, servo_channel: int = 8):
        super().__init__("Bucket")
        self.servo = Servo(servo_channel, pca, name="Bucket")
        self.open_angle = 0
        self.closed_angle = 90
        self.current_state = "closed"
        
    def open(self) -> None:
        self.servo.set_angle(self.open_angle)
        self.current_state = "open"
        logger.info("Bucket opened")
        
    def close(self) -> None:
        self.servo.set_angle(self.closed_angle)
        self.current_state = "closed"
        logger.info("Bucket closed")
        
    def activate(self) -> None:
        if self.current_state == "closed":
            self.open()
        else:
            self.close()

class Net(Tool):
    """Sample collection net tool"""
    def __init__(self, pca: PCA9685, servo_channel: int = 9):
        super().__init__("Net")
        self.servo = Servo(servo_channel, pca, name="Net")
        self.retracted_angle = 0
        self.deployed_angle = 90
        self.current_state = "retracted"
        
    def deploy(self) -> None:
        self.servo.set_angle(self.deployed_angle)
        self.current_state = "deployed"
        logger.info("Net deployed")
        
    def retract(self) -> None:
        self.servo.set_angle(self.retracted_angle)
        self.current_state = "retracted"
        logger.info("Net retracted")
        
    def activate(self) -> None:
        if self.current_state == "retracted":
            self.deploy()
        else:
            self.retract()

class Syringe(Tool):
    """Water sampling syringe tool"""
    def __init__(self, pca: PCA9685, servo_channel: int = 10):
        super().__init__("Syringe")
        self.servo = Servo(servo_channel, pca, name="Syringe")
        self.empty_angle = 0
        self.filled_angle = 90
        self.current_state = "empty"
        
    def draw(self) -> None:
        self.servo.set_angle(self.filled_angle)
        self.current_state = "filled"
        logger.info("Syringe filled")
        
    def empty(self) -> None:
        self.servo.set_angle(self.empty_angle)
        self.current_state = "empty"
        logger.info("Syringe emptied")
        
    def activate(self) -> None:
        if self.current_state == "empty":
            self.draw()
        else:
            self.empty()
