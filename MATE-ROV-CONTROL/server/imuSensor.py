from smbus2 import SMBus
import time
import struct
import math
import numpy as np
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple, List

# Configure logging
logger = logging.getLogger("ROV.Sensors.IMU")

# IMU Addresses
BNO055_ADDRESS = 0x28
LSM6DOS_ADDRESS = 0x6A
LIS3MDL_ADDRESS = 0x1C

# BNO055 Registers
BNO055_CHIP_ID = 0x00
BNO055_OPR_MODE = 0x3D
BNO055_SYS_TRIGGER = 0x3F
BNO055_PWR_MODE = 0x3E
BNO055_PAGE_ID = 0x07
BNO055_ACCEL_DATA = 0x08
BNO055_GYRO_DATA = 0x14
BNO055_MAG_DATA = 0x0E
BNO055_EULER_DATA = 0x1A
BNO055_QUATERNION_DATA = 0x20
BNO055_CALIB_STAT = 0x35  # Calibration status register

# LSM6DOS Registers
LSM6DOS_WHO_AM_I = 0x0F
LSM6DOS_CTRL1_XL = 0x10
LSM6DOS_CTRL2_G = 0x11
LSM6DOS_OUTX_L_G = 0x22
LSM6DOS_OUTX_L_XL = 0x28

# LIS3MDL Registers
LIS3MDL_WHO_AM_I = 0x0F
LIS3MDL_CTRL_REG1 = 0x20
LIS3MDL_CTRL_REG2 = 0x21
LIS3MDL_CTRL_REG3 = 0x22
LIS3MDL_CTRL_REG4 = 0x23
LIS3MDL_OUT_X_L = 0x28


class KalmanFilter:
    """
    Implements a simple Kalman filter for sensor fusion.
    This implementation is designed for attitude (orientation) estimation.
    """
    def __init__(self, state_dim, measurement_dim, process_noise=0.01, measurement_noise=0.1):
        """
        Initialize Kalman filter
        
        Args:
            state_dim: Dimension of state vector (e.g., 3 for roll/pitch/yaw)
            measurement_dim: Dimension of measurement vector
            process_noise: Process noise covariance scalar
            measurement_noise: Measurement noise covariance scalar
        """
        # State estimate and covariance
        self.x = np.zeros((state_dim, 1))  # State vector
        self.P = np.eye(state_dim)         # State covariance matrix
        
        # System matrices
        self.F = np.eye(state_dim)         # State transition model
        self.H = np.eye(measurement_dim, state_dim)  # Observation model
        
        # Noise covariances
        self.Q = process_noise * np.eye(state_dim)     # Process noise
        self.R = measurement_noise * np.eye(measurement_dim)  # Measurement noise
        
        # Identity matrix for calculations
        self.I = np.eye(state_dim)
        
    def predict(self, dt=0.01):
        """
        Predict step of the Kalman filter
        
        Args:
            dt: Time step (seconds)
        """
        # Update state transition matrix with dt
        # For simple orientation tracking, F remains identity
        
        # Predict state and covariance
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        
    def update(self, z):
        """
        Update step of the Kalman filter
        
        Args:
            z: Measurement vector
        """
        z = np.array(z).reshape(-1, 1)  # Convert to column vector
        
        # Calculate Kalman gain
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        
        # Update state and covariance
        y = z - self.H @ self.x  # Measurement residual
        self.x = self.x + K @ y
        self.P = (self.I - K @ self.H) @ self.P
        
    def get_state(self):
        """Return current state estimate"""
        return self.x.flatten()


class IMUSensorBase(ABC):
    """Base class for all IMU sensors"""
    
    def __init__(self, name: str, bus_number: int):
        self.name = name
        self.bus_number = bus_number
        self.available = False
        self.last_update_time = time.time()
        
        # Initialize the bus
        try:
            self.bus = SMBus(bus_number)
        except Exception as e:
            logger.error(f"Failed to initialize I2C bus {bus_number}: {e}")
            self.bus = None
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the sensor"""
        pass
    
    @abstractmethod
    def read_data(self) -> Dict:
        """Read data from the sensor"""
        pass
    
    def close(self) -> None:
        """Close the I2C bus connection"""
        try:
            if self.bus:
                self.bus.close()
                logger.info(f"{self.name} connection closed")
        except Exception as e:
            logger.error(f"Error closing {self.name} connection: {e}")


class BNO055Sensor(IMUSensorBase):
    """BNO055 IMU sensor implementation"""
    
    def __init__(self, bus_number: int = 7, address: int = BNO055_ADDRESS):
        super().__init__("BNO055", bus_number)
        self.address = address
        
        # Initialize calibration status
        self.calibration_status = {
            'system': 0,
            'gyro': 0,
            'accel': 0,
            'mag': 0
        }
    
    def initialize(self) -> bool:
        """Initialize the BNO055 sensor"""
        if not self.bus:
            return False
            
        try:
            # Check BNO055 chip ID
            chip_id = self.bus.read_byte_data(self.address, BNO055_CHIP_ID)
            if chip_id != 0xA0:
                logger.warning(f"Unexpected BNO055 chip ID: 0x{chip_id:02X}")
                return False
                
            logger.info(f"BNO055 detected with chip ID: 0x{chip_id:02X}")
            
            # Reset BNO055
            self.bus.write_byte_data(self.address, BNO055_SYS_TRIGGER, 0x20)
            time.sleep(0.65)  # Wait for reset
            
            # Set to config mode
            self.bus.write_byte_data(self.address, BNO055_OPR_MODE, 0x00)
            time.sleep(0.05)
            
            # Set to normal power mode
            self.bus.write_byte_data(self.address, BNO055_PWR_MODE, 0x00)
            time.sleep(0.01)
            
            # Set to page 0
            self.bus.write_byte_data(self.address, BNO055_PAGE_ID, 0x00)
            time.sleep(0.01)
            
            # Set to NDOF mode (9-axis fusion with absolute orientation)
            self.bus.write_byte_data(self.address, BNO055_OPR_MODE, 0x0C)
            time.sleep(0.02)
            
            self.available = True
            logger.info("BNO055 initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"BNO055 initialization failed: {e}")
            self.available = False
            return False
    
    def read_data(self) -> Dict:
        """Read data from BNO055 sensor"""
        if not self.available:
            return None
            
        try:
            data = {
                'accel': {'x': 0, 'y': 0, 'z': 0},
                'gyro': {'x': 0, 'y': 0, 'z': 0},
                'mag': {'x': 0, 'y': 0, 'z': 0},
                'euler': {'heading': 0, 'roll': 0, 'pitch': 0},
                'quaternion': {'w': 0, 'x': 0, 'y': 0, 'z': 0}
            }
            
            # Read calibration status
            cal_status = self.bus.read_byte_data(self.address, BNO055_CALIB_STAT)
            self.calibration_status['system'] = (cal_status >> 6) & 0x03
            self.calibration_status['gyro'] = (cal_status >> 4) & 0x03
            self.calibration_status['accel'] = (cal_status >> 2) & 0x03
            self.calibration_status['mag'] = cal_status & 0x03
            
            # Read accelerometer data (2 bytes each for x, y, z)
            accel_data = self.bus.read_i2c_block_data(self.address, BNO055_ACCEL_DATA, 6)
            data['accel']['x'] = struct.unpack('<h', bytes(accel_data[0:2]))[0] / 100.0  # m/s²
            data['accel']['y'] = struct.unpack('<h', bytes(accel_data[2:4]))[0] / 100.0
            data['accel']['z'] = struct.unpack('<h', bytes(accel_data[4:6]))[0] / 100.0
            
            # Read gyroscope data (2 bytes each for x, y, z)
            gyro_data = self.bus.read_i2c_block_data(self.address, BNO055_GYRO_DATA, 6)
            data['gyro']['x'] = struct.unpack('<h', bytes(gyro_data[0:2]))[0] / 16.0  # deg/s
            data['gyro']['y'] = struct.unpack('<h', bytes(gyro_data[2:4]))[0] / 16.0
            data['gyro']['z'] = struct.unpack('<h', bytes(gyro_data[4:6]))[0] / 16.0
            
            # Read magnetometer data (2 bytes each for x, y, z)
            mag_data = self.bus.read_i2c_block_data(self.address, BNO055_MAG_DATA, 6)
            data['mag']['x'] = struct.unpack('<h', bytes(mag_data[0:2]))[0] / 16.0  # µT
            data['mag']['y'] = struct.unpack('<h', bytes(mag_data[2:4]))[0] / 16.0
            data['mag']['z'] = struct.unpack('<h', bytes(mag_data[4:6]))[0] / 16.0
            
            # Read Euler angles data (2 bytes each for heading, roll, pitch)
            euler_data = self.bus.read_i2c_block_data(self.address, BNO055_EULER_DATA, 6)
            data['euler']['heading'] = struct.unpack('<h', bytes(euler_data[0:2]))[0] / 16.0  # degrees
            data['euler']['roll'] = struct.unpack('<h', bytes(euler_data[2:4]))[0] / 16.0
            data['euler']['pitch'] = struct.unpack('<h', bytes(euler_data[4:6]))[0] / 16.0
            
            # Read quaternion data (2 bytes each for w, x, y, z)
            quat_data = self.bus.read_i2c_block_data(self.address, BNO055_QUATERNION_DATA, 8)
            data['quaternion']['w'] = struct.unpack('<h', bytes(quat_data[0:2]))[0] / 16384.0
            data['quaternion']['x'] = struct.unpack('<h', bytes(quat_data[2:4]))[0] / 16384.0
            data['quaternion']['y'] = struct.unpack('<h', bytes(quat_data[4:6]))[0] / 16384.0
            data['quaternion']['z'] = struct.unpack('<h', bytes(quat_data[6:8]))[0] / 16384.0
            
            return data
            
        except Exception as e:
            logger.error(f"Error reading BNO055 data: {e}")
            return None
    
    def get_calibration_status(self) -> Dict:
        """Get calibration status for each sensor component"""
        return self.calibration_status
    
    def is_fully_calibrated(self) -> bool:
        """Check if the sensor is fully calibrated"""
        return (self.calibration_status['system'] == 3 and
                self.calibration_status['gyro'] == 3 and
                self.calibration_status['accel'] == 3 and
                self.calibration_status['mag'] == 3)


class LSM6DOSSensor(IMUSensorBase):
    """LSM6DOS accelerometer and gyroscope sensor implementation"""
    
    def __init__(self, bus_number: int = 7, address: int = LSM6DOS_ADDRESS):
        super().__init__("LSM6DOS", bus_number)
        self.address = address
    
    def initialize(self) -> bool:
        """Initialize the LSM6DOS sensor"""
        if not self.bus:
            return False
            
        try:
            # Check LSM6DOS ID
            who_am_i = self.bus.read_byte_data(self.address, LSM6DOS_WHO_AM_I)
            if who_am_i != 0x6C:
                logger.warning(f"Unexpected LSM6DOS ID: 0x{who_am_i:02X}")
                return False
                
            logger.info(f"LSM6DOS detected with ID: 0x{who_am_i:02X}")
            
            # Configure accelerometer: 2g range, 104 Hz
            self.bus.write_byte_data(self.address, LSM6DOS_CTRL1_XL, 0x40)
            
            # Configure gyroscope: 2000 dps, 104 Hz
            self.bus.write_byte_data(self.address, LSM6DOS_CTRL2_G, 0x4C)
            
            self.available = True
            logger.info("LSM6DOS initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"LSM6DOS initialization failed: {e}")
            self.available = False
            return False
    
    def read_data(self) -> Dict:
        """Read data from LSM6DOS sensor"""
        if not self.available:
            return None
            
        try:
            data = {
                'accel': {'x': 0, 'y': 0, 'z': 0},
                'gyro': {'x': 0, 'y': 0, 'z': 0}
            }
            
            # Read accelerometer data (2 bytes each for x, y, z)
            accel_data = self.bus.read_i2c_block_data(self.address, LSM6DOS_OUTX_L_XL, 6)
            data['accel']['x'] = struct.unpack('<h', bytes(accel_data[0:2]))[0] * 0.061 / 1000.0 * 9.81  # g to m/s²
            data['accel']['y'] = struct.unpack('<h', bytes(accel_data[2:4]))[0] * 0.061 / 1000.0 * 9.81
            data['accel']['z'] = struct.unpack('<h', bytes(accel_data[4:6]))[0] * 0.061 / 1000.0 * 9.81
            
            # Read gyroscope data (2 bytes each for x, y, z)
            gyro_data = self.bus.read_i2c_block_data(self.address, LSM6DOS_OUTX_L_G, 6)
            data['gyro']['x'] = struct.unpack('<h', bytes(gyro_data[0:2]))[0] * 70.0 / 1000.0  # mdps to deg/s
            data['gyro']['y'] = struct.unpack('<h', bytes(gyro_data[2:4]))[0] * 70.0 / 1000.0
            data['gyro']['z'] = struct.unpack('<h', bytes(gyro_data[4:6]))[0] * 70.0 / 1000.0
            
            return data
            
        except Exception as e:
            logger.error(f"Error reading LSM6DOS data: {e}")
            return None


class LIS3MDLSensor(IMUSensorBase):
    """LIS3MDL magnetometer sensor implementation"""
    
    def __init__(self, bus_number: int = 7, address: int = LIS3MDL_ADDRESS):
        super().__init__("LIS3MDL", bus_number)
        self.address = address
    
    def initialize(self) -> bool:
        """Initialize the LIS3MDL sensor"""
        if not self.bus:
            return False
            
        try:
            # Check LIS3MDL ID
            who_am_i = self.bus.read_byte_data(self.address, LIS3MDL_WHO_AM_I)
            if who_am_i != 0x3D:
                logger.warning(f"Unexpected LIS3MDL ID: 0x{who_am_i:02X}")
                return False
                
            logger.info(f"LIS3MDL detected with ID: 0x{who_am_i:02X}")
            
            # Configure magnetometer for LIS3MDL
            # CTRL_REG1: Ultra-high-performance mode for X and Y, 80Hz data rate
            self.bus.write_byte_data(self.address, LIS3MDL_CTRL_REG1, 0x72)
            
            # CTRL_REG2: ±4 gauss full scale
            self.bus.write_byte_data(self.address, LIS3MDL_CTRL_REG2, 0x00)
            
            # CTRL_REG3: Continuous conversion mode
            self.bus.write_byte_data(self.address, LIS3MDL_CTRL_REG3, 0x00)
            
            # CTRL_REG4: Ultra-high-performance mode for Z, little endian data
            self.bus.write_byte_data(self.address, LIS3MDL_CTRL_REG4, 0x0C)
            
            self.available = True
            logger.info("LIS3MDL initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"LIS3MDL initialization failed: {e}")
            self.available = False
            return False
    
    def read_data(self) -> Dict:
        """Read data from LIS3MDL sensor"""
        if not self.available:
            return None
            
        try:
            data = {
                'mag': {'x': 0, 'y': 0, 'z': 0}
            }
            
            # Read magnetometer data (2 bytes each for x, y, z)
            mag_data = self.bus.read_i2c_block_data(self.address, LIS3MDL_OUT_X_L, 6)
            scaling_factor = 0.146  # µT per LSB (for ±4 gauss)
            data['mag']['x'] = struct.unpack('<h', bytes(mag_data[0:2]))[0] * scaling_factor
            data['mag']['y'] = struct.unpack('<h', bytes(mag_data[2:4]))[0] * scaling_factor
            data['mag']['z'] = struct.unpack('<h', bytes(mag_data[4:6]))[0] * scaling_factor
            
            return data
            
        except Exception as e:
            logger.error(f"Error reading LIS3MDL data: {e}")
            return None


class IMUManager:
    """Manages multiple IMU sensors with sensor fusion"""
    
    def __init__(self, bus_number: int = 7):
        self.bus_number = bus_number
        self.sensors = {}
        
        # Initialize calibration status
        self.calibration_status = {
            'system': 0,
            'gyro': 0,
            'accel': 0,
            'mag': 0
        }
        
        # Initialize Kalman filters for orientation
        self.kalman_heading = KalmanFilter(state_dim=1, measurement_dim=1, 
                                           process_noise=0.01, measurement_noise=0.1)
        self.kalman_roll = KalmanFilter(state_dim=1, measurement_dim=1, 
                                         process_noise=0.01, measurement_noise=0.1)
        self.kalman_pitch = KalmanFilter(state_dim=1, measurement_dim=1, 
                                          process_noise=0.01, measurement_noise=0.1)
        
        # Supplementary Kalman filters for accelerometer and gyroscope data
        self.kalman_accel = KalmanFilter(state_dim=3, measurement_dim=3, 
                                         process_noise=0.01, measurement_noise=0.1)
        self.kalman_gyro = KalmanFilter(state_dim=3, measurement_dim=3, 
                                        process_noise=0.01, measurement_noise=0.1)
        
        # Last update time for calculating dt
        self.last_update_time = time.time()
        
        # Initialize the sensors
        self._init_sensors()
    
    def _init_sensors(self) -> None:
        """Initialize all available IMU sensors"""
        logger.info("Initializing IMU sensors...")
        
        # Initialize BNO055
        bno055 = BNO055Sensor(self.bus_number)
        if bno055.initialize():
            self.sensors['bno055'] = bno055
        
        # Initialize LSM6DOS
        lsm6dos = LSM6DOSSensor(self.bus_number)
        if lsm6dos.initialize():
            self.sensors['lsm6dos'] = lsm6dos
        
        # Initialize LIS3MDL
        lis3mdl = LIS3MDLSensor(self.bus_number)
        if lis3mdl.initialize():
            self.sensors['lis3mdl'] = lis3mdl
        
        # Log sensor status
        logger.info(f"IMU sensors initialized: " + 
                   f"BNO055={'bno055' in self.sensors}, " +
                   f"LSM6DOS={'lsm6dos' in self.sensors}, " +
                   f"LIS3MDL={'lis3mdl' in self.sensors}")
    
    def compute_complementary_orientation(self, accel, mag, gyro, dt):
        """
        Compute orientation using complementary filter
        Used as fallback when BNO055 is not available
        
        Args:
            accel: Accelerometer data dict with x, y, z keys
            mag: Magnetometer data dict with x, y, z keys
            gyro: Gyroscope data dict with x, y, z keys
            dt: Time step in seconds
            
        Returns:
            Dictionary with heading, roll, pitch values
        """
        # Convert to numpy arrays for easier calculations
        accel_vec = np.array([accel['x'], accel['y'], accel['z']])
        mag_vec = np.array([mag['x'], mag['y'], mag['z']])
        gyro_vec = np.array([gyro['x'], gyro['y'], gyro['z']])
        
        # Normalize accelerometer data
        accel_norm = np.linalg.norm(accel_vec)
        if accel_norm > 0:
            accel_vec = accel_vec / accel_norm
        
        # Calculate roll and pitch from accelerometer
        roll_acc = math.atan2(accel_vec[1], accel_vec[2])
        pitch_acc = math.atan2(-accel_vec[0], 
                              math.sqrt(accel_vec[1]**2 + accel_vec[2]**2))
        
        # Calculate heading from magnetometer with tilt compensation
        sin_roll = math.sin(roll_acc)
        cos_roll = math.cos(roll_acc)
        sin_pitch = math.sin(pitch_acc)
        cos_pitch = math.cos(pitch_acc)
        
        # Tilt-compensated magnetic field
        mag_x = mag_vec[0] * cos_pitch + mag_vec[2] * sin_pitch
        mag_y = mag_vec[0] * sin_roll * sin_pitch + mag_vec[1] * cos_roll - mag_vec[2] * sin_roll * cos_pitch
        
        # Calculate heading
        heading = math.atan2(mag_y, mag_x)
        # Convert to degrees and handle negative values
        heading = math.degrees(heading)
        if heading < 0:
            heading += 360.0
            
        # Convert roll and pitch to degrees
        roll = math.degrees(roll_acc)
        pitch = math.degrees(pitch_acc)
        
        return {
            'heading': heading,
            'roll': roll,
            'pitch': pitch
        }
    
    def update_kalman_filters(self, bno055_data, lsm6dos_data, lis3mdl_data):
        """
        Update Kalman filters with new sensor data
        
        Args:
            bno055_data: Data from BNO055 sensor
            lsm6dos_data: Data from LSM6DOS sensor
            lis3mdl_data: Data from LIS3MDL sensor
            
        Returns:
            Dictionary with fused orientation data
        """
        # Calculate time step
        current_time = time.time()
        dt = current_time - self.last_update_time
        self.last_update_time = current_time
        
        # Ensure dt is positive and reasonable
        dt = max(0.001, min(dt, 0.1))
        
        # Fused orientation data structure
        fused_data = {
            'orientation': {
                'heading': 0.0,
                'roll': 0.0,
                'pitch': 0.0
            },
            'quaternion': {
                'w': 0.0,
                'x': 0.0,
                'y': 0.0,
                'z': 0.0
            },
            'accel': {
                'x': 0.0,
                'y': 0.0,
                'z': 0.0
            },
            'gyro': {
                'x': 0.0,
                'y': 0.0,
                'z': 0.0
            },
            'calibration': self.calibration_status,
            'sensor_status': {
                'bno055': 'bno055' in self.sensors,
                'lsm6dos': 'lsm6dos' in self.sensors,
                'lis3mdl': 'lis3mdl' in self.sensors
            }
        }
        
        # Update orientation Kalman filters
        if bno055_data:
            # BNO055 provides direct orientation data
            bno_euler = bno055_data['euler']
            
            # Predict step for each Kalman filter
            self.kalman_heading.predict(dt)
            self.kalman_roll.predict(dt)
            self.kalman_pitch.predict(dt)
            
            # Update step with BNO055 measurements
            self.kalman_heading.update([bno_euler['heading']])
            self.kalman_roll.update([bno_euler['roll']])
            self.kalman_pitch.update([bno_euler['pitch']])
            
            # Copy quaternion data directly
            fused_data['quaternion'] = bno055_data['quaternion']
            
            # Update calibration status
            if 'bno055' in self.sensors:
                self.calibration_status = self.sensors['bno055'].get_calibration_status()
        
        # Compute orientation if we have both accelerometer and magnetometer data
        if (lsm6dos_data and lis3mdl_data) or not bno055_data:
            # Fallback to accelerometer + magnetometer based orientation
            if lsm6dos_data and lis3mdl_data:
                accel = lsm6dos_data['accel']
                gyro = lsm6dos_data['gyro']
                mag = lis3mdl_data['mag']
                
                # Compute orientation using complementary filter
                comp_orientation = self.compute_complementary_orientation(accel, mag, gyro, dt)
                
                # Only use this data if BNO055 is not available
                if not bno055_data:
                    # Predict step for each Kalman filter
                    self.kalman_heading.predict(dt)
                    self.kalman_roll.predict(dt)
                    self.kalman_pitch.predict(dt)
                    
                    # Update step with computed orientation
                    self.kalman_heading.update([comp_orientation['heading']])
                    self.kalman_roll.update([comp_orientation['roll']])
                    self.kalman_pitch.update([comp_orientation['pitch']])
        
        # Update acceleration and gyro Kalman filters
        accel_measurements = []
        gyro_measurements = []
        
        if bno055_data:
            accel_measurements.append([
                bno055_data['accel']['x'],
                bno055_data['accel']['y'],
                bno055_data['accel']['z']
            ])
            
            gyro_measurements.append([
                bno055_data['gyro']['x'],
                bno055_data['gyro']['y'],
                bno055_data['gyro']['z']
            ])
        
        if lsm6dos_data:
            accel_measurements.append([
                lsm6dos_data['accel']['x'],
                lsm6dos_data['accel']['y'],
                lsm6dos_data['accel']['z']
            ])
            
            gyro_measurements.append([
                lsm6dos_data['gyro']['x'],
                lsm6dos_data['gyro']['y'],
                lsm6dos_data['gyro']['z']
            ])
        
        # Only update filters if we have measurement data
        if accel_measurements:
            # Average the acceleration measurements
            avg_accel = np.mean(accel_measurements, axis=0)
            
            # Predict and update acceleration Kalman filter
            self.kalman_accel.predict(dt)
            self.kalman_accel.update(avg_accel)
            
            # Store fused acceleration data
            accel_state = self.kalman_accel.get_state()
            fused_data['accel']['x'] = accel_state[0]
            fused_data['accel']['y'] = accel_state[1]
            fused_data['accel']['z'] = accel_state[2]
        
        if gyro_measurements:
            # Average the gyro measurements
            avg_gyro = np.mean(gyro_measurements, axis=0)
            
            # Predict and update gyro Kalman filter
            self.kalman_gyro.predict(dt)
            self.kalman_gyro.update(avg_gyro)
            
            # Store fused gyro data
            gyro_state = self.kalman_gyro.get_state()
            fused_data['gyro']['x'] = gyro_state[0]
            fused_data['gyro']['y'] = gyro_state[1]
            fused_data['gyro']['z'] = gyro_state[2]
        
        # Get filtered orientation values
        fused_data['orientation']['heading'] = self.kalman_heading.get_state()[0]
        fused_data['orientation']['roll'] = self.kalman_roll.get_state()[0]
        fused_data['orientation']['pitch'] = self.kalman_pitch.get_state()[0]
        
        # Normalize heading to 0-360
        fused_data['orientation']['heading'] = fused_data['orientation']['heading'] % 360.0
        
        return fused_data
    
    def read_data(self) -> Dict:
        """
        Read data from all available sensors and fuse with Kalman filters
        
        Returns:
            Dictionary with fused orientation and motion data
        """
        # Read data from each sensor
        sensor_data = {}
        
        for name, sensor in self.sensors.items():
            sensor_data[name] = sensor.read_data()
        
        # Update Kalman filters and get fused data
        bno055_data = sensor_data.get('bno055')
        lsm6dos_data = sensor_data.get('lsm6dos')
        lis3mdl_data = sensor_data.get('lis3mdl')
        
        fused_data = self.update_kalman_filters(bno055_data, lsm6dos_data, lis3mdl_data)
        return fused_data
    
    def get_orientation(self) -> Tuple[float, float, float]:
        """
        Get current orientation (heading, roll, pitch)
        
        Returns:
            Tuple of (heading, roll, pitch) in degrees
        """
        data = self.read_data()
        return (
            data['orientation']['heading'],
            data['orientation']['roll'],
            data['orientation']['pitch']
        )
    
    def get_quaternion(self) -> Dict:
        """
        Get current orientation as quaternion
        
        Returns:
            Dictionary with quaternion components w, x, y, z
        """
        data = self.read_data()
        return data['quaternion']
    
    def get_calibration_status(self) -> Dict:
        """
        Get calibration status for each sensor component
        
        Returns:
            Dictionary with calibration status (0-3) for system, gyro, accel, mag
        """
        return self.calibration_status
    
    def is_fully_calibrated(self) -> bool:
        """
        Check if the IMU is fully calibrated
        
        Returns:
            Boolean indicating if all components are fully calibrated (level 3)
        """
        if 'bno055' in self.sensors:
            return self.sensors['bno055'].is_fully_calibrated()
        return False
    
    def close(self) -> None:
        """Close all sensor connections"""
        for sensor in self.sensors.values():
            sensor.close()
        logger.info("All IMU sensors closed")


# For testing as a standalone module
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize the IMU manager
    imu_manager = IMUManager(bus_number=7)
    
    try:
        # Read and print IMU data continuously
        print("Reading IMU data... Press Ctrl+C to exit")
        while True:
            data = imu_manager.read_data()
            
            print("\n=== Fused Orientation Data ===")
            print(f"Heading: {data['orientation']['heading']:.2f}°")
            print(f"Roll: {data['orientation']['roll']:.2f}°")
            print(f"Pitch: {data['orientation']['pitch']:.2f}°")
            
            print("\n=== Acceleration Data ===")
            print(f"X: {data['accel']['x']:.2f} m/s²")
            print(f"Y: {data['accel']['y']:.2f} m/s²")
            print(f"Z: {data['accel']['z']:.2f} m/s²")
            
            print("\n=== Gyroscope Data ===")
            print(f"X: {data['gyro']['x']:.2f} deg/s")
            print(f"Y: {data['gyro']['y']:.2f} deg/s")
            print(f"Z: {data['gyro']['z']:.2f} deg/s")
            
            print("\n=== Calibration Status ===")
            print(f"System: {data['calibration']['system']}/3")
            print(f"Gyro: {data['calibration']['gyro']}/3")
            print(f"Accel: {data['calibration']['accel']}/3")
            print(f"Mag: {data['calibration']['mag']}/3")
            
            time.sleep(0.2)  # Update every 200ms
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        imu_manager.close()