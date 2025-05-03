# hardware/thruster.py
from hardware.pca9685 import PCA9685, PCA9685Channel
import logging
from time import sleep
from typing import Dict

# --------------------------- Thruster Class ---------------------------
class Thruster:
    """Electronic Speed Controller (ESC) for thrusters."""
    def __init__(self, channel: int, pca: PCA9685, name: str = "thruster"):
        self.channel = channel
        self.pca = pca
        self.name = name
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1300  # Reverse max pulse
        self.MAX_PULSE = 1700  # Forward max pulse
        self.FORWARD_MIN = 1525  # Minimum pulse to start forward motion
        self.REVERSE_MAX = 1475  # Maximum pulse to start reverse motion
        self.current_pulse = self.STOP_PULSE
        self.current_speed = 0.0  # Speed in range -1.0 to 1.0
        
        # For logging activity
        self.last_speed_change = time.time()
        self.total_active_time = 0.0
        self.direction_changes = 0
        logger.debug(f"Created thruster '{self.name}' on channel {self.channel}")

    def initialize(self) -> None:
        """Initialize ESC with neutral signal."""
        self._set_pulse_width(self.STOP_PULSE)
        sleep(2)
        logger.info(f"Thruster {self.name} on channel {self.channel} initialized")

    def set_speed(self, speed: float) -> None:
        """
        Set thruster speed (-1.0 for full reverse, +1.0 for full forward; 0.0 stops).
        """
        speed = max(-1.0, min(1.0, speed))
        
        if speed > 0:
            pulse_width = self.FORWARD_MIN + (speed * (self.MAX_PULSE - self.FORWARD_MIN))
        elif speed < 0:
            pulse_width = self.REVERSE_MAX - (abs(speed) * (self.REVERSE_MAX - self.MIN_PULSE))
        else:
            pulse_width = self.STOP_PULSE
            
        # Log direction change if applicable
        if (self.current_speed > 0 and speed < 0) or (self.current_speed < 0 and speed > 0):
            self.direction_changes += 1
            logger.debug(f"Thruster {self.name}: Direction change #{self.direction_changes}")
            
        # Update only when speed has changed
        if speed != self.current_speed:
            now = time.time()
            if self.current_speed != 0:
                active_time = now - self.last_speed_change
                self.total_active_time += active_time
            # logger.info(f"Thruster {self.name}: {self.current_speed:.2f} -> {speed:.2f} (pulse: {int(pulse_width)})")
            self.current_speed = speed
            self.last_speed_change = now
            self._set_pulse_width(int(pulse_width))
        
    def _set_pulse_width(self, pulse_width: int) -> None:
        """Set ESC pulse width."""
        offset = 9
        pulse_width += offset
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        self.current_pulse = pulse_width
        sleep(0.001)

    def stop(self) -> None:
        """Stop the thruster."""
        prev_speed = self.current_speed
        self.set_speed(0.0)
        logger.info(f"Thruster {self.name} stopped (was: {prev_speed:.2f})")

    def get_stats(self) -> Dict:
        """Return statistics for this thruster."""
        return {
            "name": self.name,
            "channel": self.channel,
            "current_speed": self.current_speed,
            "current_pulse": self.current_pulse,
            "total_active_time": self.total_active_time,
            "direction_changes": self.direction_changes
        }