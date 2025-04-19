# hardware/servo.py
from hardware.pca9685 import PCA9685
import time
import logging

logger = logging.getLogger("Servo")

class Servo:
    """Generic servo motor controller"""
    def __init__(self, channel: int, pca: PCA9685, min_pulse: int = 900, max_pulse: int = 2100, name: str = "unnamed"):
        self.channel = channel
        self.pca = pca
        self.min_pulse = min_pulse
        self.max_pulse = max_pulse
        self.current_pulse = 1500  # Neutral position
        self.name = name
        self.last_angle = 90  # Default middle position
        
    def set_angle(self, angle: float) -> None:
        """Set servo position using angle (0-180°)"""
        angle = max(0, min(180, angle))
        value = (angle / 90.0) - 1.0
        pulse_width = self._map_value_to_pulse(value)
        self._set_pulse_width(pulse_width)
        self.last_angle = angle
        logger.debug(f"Servo {self.name}: set to angle {angle}°")
        
    def _map_value_to_pulse(self, value: float) -> int:
        value = max(-1.0, min(1.0, value))
        return int(self.min_pulse + (value + 1) * (self.max_pulse - self.min_pulse) / 2)
        
    def _set_pulse_width(self, pulse_width: int) -> None:
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        logger.debug(f"{self.name} (Ch {self.channel}): {pulse_width} µs -> duty {duty_cycle}")
        self.current_pulse = pulse_width
        time.sleep(0.001)
