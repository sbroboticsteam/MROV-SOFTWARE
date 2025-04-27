# sensor.py
import threading
import time
import random
import logging
from imuSensor import IMUManager  # Assuming this file/module exists
from depth import DepthSensor   # Assuming this file/module exists

logger = logging.getLogger("Sensor")

class Sensor:
    """Manages all sensor systems for the ROV"""
    def __init__(self):
        logger.info("Initializing sensor systems...")
        self.imu = IMUManager(bus_number=7)
        self.depth_sensor = DepthSensor()
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.depth = 0.0
        self.temperature = 20.0
        self.voltage = 12.0
        self.current = 0.0
        self.running = False
        self.sensor_thread = None
        self.last_log_time = time.time()
        self.log_interval = 1.0
        logger.info("Sensor systems initialized")
    
    def start(self) -> None:
        self.running = True
        self.sensor_thread = threading.Thread(target=self._sensor_loop, daemon=True)
        self.sensor_thread.start()
        logger.info("Sensor data acquisition started")
    
    def _sensor_loop(self) -> None:
        prev_roll, prev_pitch, prev_yaw = 0.0, 0.0, 0.0
        prev_depth = 0.0
        while self.running:
            try:
                heading, roll, pitch = self.imu.get_orientation()
                roll_change = abs(roll - prev_roll)
                pitch_change = abs(pitch - prev_pitch)
                yaw_change = abs(heading - prev_yaw)
                if roll_change > 2.0 or pitch_change > 2.0 or yaw_change > 5.0:
                    logger.info(f"IMU MOTION DETECTED - Roll: {prev_roll:.1f}° → {roll:.1f}°, "
                                f"Pitch: {prev_pitch:.1f}° → {pitch:.1f}°, "
                                f"Yaw: {prev_yaw:.1f}° → {heading:.1f}°")
                prev_roll, prev_pitch, prev_yaw = roll, pitch, heading
                self.yaw = heading
                self.roll = roll
                self.pitch = pitch
                self.depth = self.depth_sensor.get_depth()
                depth_change = abs(self.depth - prev_depth)
                if depth_change > 0.1:
                    logger.info(f"DEPTH CHANGE DETECTED: {prev_depth:.2f}m → {self.depth:.2f}m")
                prev_depth = self.depth
                self.temperature = self.depth_sensor.get_temperature()
                current_time = time.time()
                if current_time - self.last_log_time >= self.log_interval:
                    self.last_log_time = current_time
                    cal_status = self.imu.get_calibration_status()
                    logger.debug(f"Orientation: Roll={self.roll:.1f}°, Pitch={self.pitch:.1f}°, "
                                 f"Yaw={self.yaw:.1f}°, Depth={self.depth:.2f}m")
                    logger.debug(f"IMU Calibration - Sys:{cal_status['system']}/3, Gyro:{cal_status['gyro']}/3, "
                                 f"Accel:{cal_status['accel']}/3, Mag:{cal_status['mag']}/3")
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"Error in sensor loop: {e}")
                time.sleep(0.5)
    
    def _update_power_status(self) -> None:
        self.voltage = 12.0 - (random.random() * 0.5)
        self.current = 1.0 + (random.random() * 4.0)
    
    def get_orientation(self) -> tuple:
        return self.roll, self.pitch, self.yaw
    
    def get_depth(self) -> float:
        return self.depth
    
    def get_temperature(self) -> float:
        return self.temperature
    
    def get_power_status(self) -> tuple:
        return self.voltage, self.current
    
    def get_telemetry(self) -> dict:
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
    
    def get_calibration_status(self) -> dict:
        return self.imu.get_calibration_status()
    
    def is_fully_calibrated(self) -> bool:
        return self.imu.is_fully_calibrated()
    
    def shutdown(self) -> None:
        logger.info("Sensor systems shutting down")
        self.running = False
        if self.sensor_thread and self.sensor_thread.is_alive():
            self.sensor_thread.join(timeout=2.0)
        self.imu.close()
        logger.info("Sensor systems shutdown complete")
