import time
import logging

# Configure module logger
logger = logging.getLogger("IMU")

# Try to import BNO055
try:
    from bno055 import BNO055, BNO055_ADDRESS_A
    BNO055_AVAILABLE = True
    logger.info("BNO055 module successfully imported")
except ImportError:
    BNO055_AVAILABLE = False
    logger.warning("Could not import BNO055 class. IMU functionality will be limited.")
    BNO055 = None

class IMUSensor:
    """Interface to the BNO055 IMU sensor for orientation sensing."""
    def __init__(self, bus_number=7, address=BNO055_ADDRESS_A if BNO055_AVAILABLE else None):
        self.bno = None
        self.available = False
        self.last_read_time = 0
        self.read_interval = 0.02  # 50Hz max reading rate
        self.last_heading = 0
        self.last_roll = 0
        self.last_pitch = 0
        self.calibration_status = (0, 0, 0, 0)  # sys, gyro, accel, mag
        
        if BNO055_AVAILABLE and address:
            try:
                logger.info("Initializing BNO055 sensor...")
                self.bno = BNO055(bus_number=bus_number, address=address)
                if not self.bno.begin():
                    logger.error("Failed to initialize BNO055!")
                    self.available = False
                else:
                    logger.info("BNO055 Initialized Successfully.")
                    # Check initial calibration
                    time.sleep(1)  # Wait a bit after init
                    self.calibration_status = self.bno.get_calibration()
                    logger.info(f"Initial Calibration: Sys={self.calibration_status[0]}, "
                                f"Gyro={self.calibration_status[1]}, "
                                f"Accel={self.calibration_status[2]}, "
                                f"Mag={self.calibration_status[3]}")
                    self.available = True
                    
                    # Initial read
                    self._read_orientation()
            except Exception as e:
                logger.error(f"Exception during BNO055 initialization: {e}")
                self.available = False
        else:
            logger.warning("BNO055 not available. Orientation sensing disabled.")
            self.available = False
    
    def _read_orientation(self):
        """Read the current orientation from the BNO055 sensor."""
        if not self.available or not self.bno:
            return self.last_heading, self.last_roll, self.last_pitch
            
        current_time = time.time()
        # Throttle reads to avoid overwhelming the I2C bus
        if current_time - self.last_read_time < self.read_interval:
            return self.last_heading, self.last_roll, self.last_pitch
            
        try:
            # Get Euler angles in degrees
            heading, roll, pitch = self.bno.get_euler()
            
            # Update last read values
            self.last_heading = heading
            self.last_roll = roll
            self.last_pitch = pitch
            self.last_read_time = current_time
            
            # Periodically update calibration status
            if current_time % 5 < 0.1:  # Every ~5 seconds
                self.calibration_status = self.bno.get_calibration()
                
            return heading, roll, pitch
            
        except Exception as e:
            logger.error(f"Error reading orientation: {e}")
            return self.last_heading, self.last_roll, self.last_pitch
    
    def get_orientation(self):
        """Get the current orientation (heading, roll, pitch) in degrees."""
        if self.available:
            return self._read_orientation()
        return 0, 0, 0  # Default values if not available
    
    def get_calibration_status(self):
        """Get current calibration status (sys, gyro, accel, mag)."""
        if self.available:
            try:
                self.calibration_status = self.bno.get_calibration()
            except Exception as e:
                logger.error(f"Error reading calibration status: {e}")
        return self.calibration_status
    
    def is_calibrated(self, min_sys=2, min_gyro=3, min_accel=2, min_mag=2):
        """Check if the sensor is adequately calibrated."""
        if not self.available:
            return False
            
        sys, gyro, accel, mag = self.get_calibration_status()
        return (sys >= min_sys and gyro >= min_gyro and 
                accel >= min_accel and mag >= min_mag)
    
    def close(self):
        """Close connection to the sensor."""
        if self.available and self.bno:
            try:
                self.bno.close()
                logger.info("IMU sensor connection closed")
            except Exception as e:
                logger.error(f"Error closing IMU sensor: {e}")