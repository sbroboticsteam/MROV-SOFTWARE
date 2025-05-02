import time
import logging
import argparse
import sys
import numpy as np
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"imu_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("IMU_TEST")

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
            
            # Apply calibration offset to roll value (2.69 degrees when level)
            roll += 2.69
            pitch -= 8.44
            
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

def visualize_orientation(heading, roll, pitch):
    """Create a simple text visualization of the orientation"""
    heading_arrow = int((heading / 360) * 16)
    roll_bar = int(((roll + 180) / 360) * 20)
    pitch_bar = int(((pitch + 90) / 180) * 20)
    
    compass = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
               "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    
    heading_display = f"Heading: {heading:7.2f}° {compass[heading_arrow % 16]}"
    roll_display = f"Roll:    {roll:7.2f}° {'|' * roll_bar}"
    pitch_display = f"Pitch:   {pitch:7.2f}° {'|' * pitch_bar}"
    
    return f"\n{heading_display}\n{roll_display}\n{pitch_display}"

def test_imu_sensor(bus_number=7, sample_rate=10):
    """Test the IMU sensor continuously until interrupted"""
    logger.info(f"Starting continuous IMU test on bus {bus_number}")
    
    # Create sensor instance
    imu = IMUSensor(bus_number=bus_number)
    
    if not imu.available:
        logger.error("IMU sensor not available. Test aborted.")
        return
    
    logger.info("IMU sensor initialized successfully")
    logger.info("Test will run continuously. Press Ctrl+C to stop.")
    
    # Track stats for analysis
    readings = []
    start_time = time.time()
    last_cal_report_time = 0
    
    try:
        # Run continuous loop without time limit
        while True:
            # Get current orientation
            heading, roll, pitch = imu.get_orientation()
            current_time = time.time() - start_time
            
            # Store reading (limit to last 1000 samples to avoid memory issues)
            readings.append((current_time, heading, roll, pitch))
            if len(readings) > 1000:
                readings.pop(0)
            
            # Log values
            logger.info(f"Time: {current_time:.2f}s | Heading: {heading:.2f}° | "
                       f"Roll: {roll:.2f}° | Pitch: {pitch:.2f}°")
            
            # Display visualization
            vis = visualize_orientation(heading, roll, pitch)
            print(f"\033[H\033[J{vis}")  # Clear screen and show visualization
            
            # Report calibration status every 5 seconds
            if time.time() - last_cal_report_time > 5:
                sys, gyro, accel, mag = imu.get_calibration_status()
                logger.info(f"Calibration Status - Sys: {sys}/3, Gyro: {gyro}/3, "
                           f"Accel: {accel}/3, Mag: {mag}/3")
                
                if sys == 3 and gyro == 3 and accel == 3 and mag == 3:
                    logger.info("*** FULLY CALIBRATED ***")
                
                last_cal_report_time = time.time()
            
            # Wait for next sample
            time.sleep(1.0 / sample_rate)
    
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Error during IMU test: {e}")
    finally:
        # Clean up
        imu.close()
        logger.info("IMU test completed")
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test BNO055 IMU Sensor")
    parser.add_argument("--bus", type=int, default=7, help="I2C bus number")
    parser.add_argument("--rate", type=int, default=10, help="Sample rate in Hz")
    args = parser.parse_args()
    
    try:
        print("Starting continuous IMU test (press Ctrl+C to exit)")
        test_imu_sensor(bus_number=args.bus, sample_rate=args.rate)
    except Exception as e:
        logger.error(f"Error in main program: {e}")