# hardware/thruster.py
import time
from hardware.pca9685 import PCA9685
import logging

logger = logging.getLogger("Thruster")

class Thruster:
    """Electronic Speed Controller (ESC) for thrusters"""
    
    def __init__(self, channel: int, pca: PCA9685, name: str = "thruster"):
        self.channel = channel
        self.pca = pca
        self.name = name
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1100
        self.MAX_PULSE = 1900
        self.FORWARD_MIN = 1525
        self.REVERSE_MAX = 1475
        self.current_pulse = self.STOP_PULSE
        self.current_speed = 0.0
        self.last_speed_change = time.time()
        self.total_active_time = 0.0
        self.direction_changes = 0
        
        logger.debug(f"Created thruster '{self.name}' on channel {self.channel}")

    def initialize(self) -> None:
        self._set_pulse_width(self.STOP_PULSE)
        time.sleep(2)
        logger.info(f"Thruster {self.name} on channel {self.channel} initialized")

    def set_speed(self, speed: float) -> None:
        speed = max(-1.0, min(1.0, speed))
        if speed > 0:
            pulse_width = self.FORWARD_MIN + (speed * (self.MAX_PULSE - self.FORWARD_MIN))
        elif speed < 0:
            pulse_width = self.REVERSE_MAX - (abs(speed) * (self.REVERSE_MAX - self.MIN_PULSE))
        else:
            pulse_width = self.STOP_PULSE
            
        if (self.current_speed > 0 and speed < 0) or (self.current_speed < 0 and speed > 0):
            self.direction_changes += 1
            logger.debug(f"Thruster {self.name}: Direction change #{self.direction_changes}")
            
        if speed != self.current_speed:
            now = time.time()
            if self.current_speed != 0:
                active_time = now - self.last_speed_change
                self.total_active_time += active_time
            logger.info(f"Thruster {self.name}: {self.current_speed:.2f} → {speed:.2f} (pulse: {int(pulse_width)})")
            self.current_speed = speed
            self.last_speed_change = now
            self._set_pulse_width(int(pulse_width))
        
    def _set_pulse_width(self, pulse_width: int) -> None:
        offset = 9
        pulse_width += offset
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        self.current_pulse = pulse_width
        time.sleep(0.001)

    def stop(self) -> None:
        prev_speed = self.current_speed
        self.set_speed(0.0)
        logger.info(f"Thruster {self.name} stopped (was: {prev_speed:.2f})")
