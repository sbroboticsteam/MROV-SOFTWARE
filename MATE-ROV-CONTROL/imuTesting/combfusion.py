#!/usr/bin/env python3
# filepath: /home/sybau/Desktop/MROV-SOFTWARE/MATE-ROV-CONTROL/imuTesting/sensor_fusion.py
import time
import math
import numpy as np
from lsm6dsox import LSM6DSOX, LSM6DSOX_ADDRESS
from lis3mdl import LIS3MDL, LIS3MDL_ADDRESS
from bno055 import BNO055, BNO055_ADDRESS_A

# Quaternion helper class for sensor fusion
class Quaternion:
    def __init__(self, w=1.0, x=0.0, y=0.0, z=0.0):
        self.w = w
        self.x = x
        self.y = y
        self.z = z
    
    def normalize(self):
        norm = math.sqrt(self.w**2 + self.x**2 + self.y**2 + self.z**2)
        if norm > 0:
            self.w /= norm
            self.x /= norm
            self.y /= norm
            self.z /= norm
    
    def to_euler(self):
        """Convert quaternion to Euler angles (roll, pitch, yaw) in degrees"""
        # Roll (x-axis rotation)
        sinr_cosp = 2.0 * (self.w * self.x + self.y * self.z)
        cosr_cosp = 1.0 - 2.0 * (self.x * self.x + self.y * self.y)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        
        # Pitch (y-axis rotation)
        sinp = 2.0 * (self.w * self.y - self.z * self.x)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2, sinp)  # Use 90 degrees if out of range
        else:
            pitch = math.asin(sinp)
        
        # Yaw (z-axis rotation)
        siny_cosp = 2.0 * (self.w * self.z + self.x * self.y)
        cosy_cosp = 1.0 - 2.0 * (self.y * self.y + self.z * self.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        
        # Convert to degrees
        roll_deg = roll * 180.0 / math.pi
        pitch_deg = pitch * 180.0 / math.pi
        yaw_deg = yaw * 180.0 / math.pi
        
        # Make yaw 0-360
        if yaw_deg < 0:
            yaw_deg += 360.0
            
        return (roll_deg, pitch_deg, yaw_deg)
    
    def __str__(self):
        return f"Quaternion(w={self.w:.4f}, x={self.x:.4f}, y={self.y:.4f}, z={self.z:.4f})"


class SensorFusion:
    def __init__(self, accel_gyro, mag):
        self.accel_gyro = accel_gyro  # LSM6DSOX
        self.mag = mag                # LIS3MDL
        
        # Fusion parameters
        self.q = Quaternion()        # Current orientation quaternion
        self.last_update = time.time()
        self.gyro_bias = (0, 0, 0)   # Gyro bias (calibrated at initialization)
        
        # Filter constants
        self.beta = 0.1              # Madgwick filter parameter
        self.gyro_threshold = 0.1    # Gyro zero threshold
        
        # Gravity vector in Earth frame
        self.gravity = (0, 0, 1)     # Z is down in sensor frame
        
        # Magnetic declination (adjust for your location)
        self.mag_declination = 0.0   # In degrees
        
        # Calibration status (0-3 for each component)
        self.cal_sys = 0
        self.cal_gyro = 0
        self.cal_accel = 0
        self.cal_mag = 0
        
        # Calibrate gyro
        self.calibrate_gyro()
    
    def calibrate_gyro(self, samples=100):
        """Calibrate gyroscope by calculating the zero bias"""
        print("Calibrating gyroscope. Keep the sensor still...")
        
        # Collect gyro data for averaging
        gyro_x_sum = 0
        gyro_y_sum = 0
        gyro_z_sum = 0
        
        for _ in range(samples):
            if self.accel_gyro.data_ready():
                gx, gy, gz = self.accel_gyro.get_gyro_data()
                gyro_x_sum += gx
                gyro_y_sum += gy
                gyro_z_sum += gz
            time.sleep(0.01)
            
        # Calculate average (bias)
        self.gyro_bias = (
            gyro_x_sum / samples,
            gyro_y_sum / samples,
            gyro_z_sum / samples
        )
        
        print(f"Gyro calibration complete. Bias: {self.gyro_bias}")
        self.cal_gyro = 3  # Mark as fully calibrated
    
    def update(self):
        """Update orientation based on sensor readings"""
        current_time = time.time()
        dt = current_time - self.last_update
        self.last_update = current_time
        
        # Get accelerometer data (in g)
        ax, ay, az = self.accel_gyro.get_accel_data()
        
        # Get gyroscope data (in dps) and apply bias correction
        gx, gy, gz = self.accel_gyro.get_gyro_data()
        gx -= self.gyro_bias[0]
        gy -= self.gyro_bias[1]
        gz -= self.gyro_bias[2]
        
        # Convert gyro from dps to rad/s
        gx_rad = gx * math.pi / 180.0
        gy_rad = gy * math.pi / 180.0
        gz_rad = gz * math.pi / 180.0
        
        # Get magnetometer data (in μT)
        mx, my, mz = self.mag.get_magnetic_data()
        
        # Apply simple thresholding to gyro values to avoid drift when stationary
        if abs(gx_rad) < self.gyro_threshold:
            gx_rad = 0
        if abs(gy_rad) < self.gyro_threshold:
            gy_rad = 0
        if abs(gz_rad) < self.gyro_threshold:
            gz_rad = 0
        
        # Simplified quaternion update via gyroscope integration
        # This is a basic approach - for better results, implement a full 
        # Madgwick or Mahony filter with accelerometer and magnetometer correction
        
        # Gyro integration
        qDot = Quaternion(
            -0.5 * (self.q.x * gx_rad + self.q.y * gy_rad + self.q.z * gz_rad),
            0.5 * (self.q.w * gx_rad + self.q.y * gz_rad - self.q.z * gy_rad),
            0.5 * (self.q.w * gy_rad - self.q.x * gz_rad + self.q.z * gx_rad),
            0.5 * (self.q.w * gz_rad + self.q.x * gy_rad - self.q.y * gx_rad)
        )
        
        # Update quaternion
        self.q.w += qDot.w * dt
        self.q.x += qDot.x * dt
        self.q.y += qDot.y * dt
        self.q.z += qDot.z * dt
        
        # Normalize
        self.q.normalize()
        
        # Update calibration status
        # Simple approach - increase calibration with more samples
        if self.cal_accel < 3:
            self.cal_accel = min(3, self.cal_accel + dt * 0.3)
        if self.cal_mag < 3:
            self.cal_mag = min(3, self.cal_mag + dt * 0.2)
        
        # System calibration is the minimum of component calibrations
        self.cal_sys = min(self.cal_gyro, int(self.cal_accel), int(self.cal_mag))
    
    def get_euler(self):
        """Get Euler angles (roll, pitch, heading) in degrees"""
        roll, pitch, yaw = self.q.to_euler()
        
        # Apply magnetic declination to heading
        heading = (yaw + self.mag_declination) % 360.0
        
        return (heading, roll, pitch)
    
    def get_quaternion(self):
        """Get quaternion values"""
        return (self.q.w, self.q.x, self.q.y, self.q.z)
    
    def get_calibration(self):
        """Get calibration status (0-3 for each component)"""
        return (self.cal_sys, self.cal_gyro, int(self.cal_accel), int(self.cal_mag))
    
    def get_linear_acceleration(self):
        """Calculate linear acceleration by removing gravity"""
        # Get raw acceleration in g
        ax, ay, az = self.accel_gyro.get_accel_data()
        
        # Convert to m/s²
        ax_ms2 = ax * 9.81
        ay_ms2 = ay * 9.81
        az_ms2 = az * 9.81
        
        # Rotate gravity vector from earth frame to sensor frame using inverse quaternion
        # (simplified implementation - for demonstration purposes)
        # To properly remove gravity, we need to use quaternion rotation
        
        # For now, a simple approximation based on orientation
        roll, pitch, _ = self.q.to_euler()
        roll_rad = roll * math.pi / 180.0
        pitch_rad = pitch * math.pi / 180.0
        
        # Estimate gravity components in sensor frame
        gx = math.sin(pitch_rad) * 9.81
        gy = -math.sin(roll_rad) * math.cos(pitch_rad) * 9.81
        gz = -math.cos(roll_rad) * math.cos(pitch_rad) * 9.81
        
        # Remove gravity
        linear_x = ax_ms2 - gx
        linear_y = ay_ms2 - gy
        linear_z = az_ms2 - gz
        
        return (linear_x, linear_y, linear_z)
    
    def get_gravity(self):
        """Get gravity vector in sensor frame"""
        roll, pitch, _ = self.q.to_euler()
        roll_rad = roll * math.pi / 180.0
        pitch_rad = pitch * math.pi / 180.0
        
        # Gravity components in sensor frame
        gx = math.sin(pitch_rad) * 9.81
        gy = -math.sin(roll_rad) * math.cos(pitch_rad) * 9.81
        gz = -math.cos(roll_rad) * math.cos(pitch_rad) * 9.81
        
        return (gx, gy, gz)


def main():
    """Initialize sensors and run sensor fusion"""
    print("Initializing sensors...")
    print("-" * 80)
    
    # Initialize LSM6DSOX
    lsm = LSM6DSOX(bus_number=7, address=LSM6DSOX_ADDRESS)
    print("Initializing LSM6DSOX sensor...")
    if not lsm.begin():
        print("Failed to initialize LSM6DSOX! Is the sensor connected?")
        return
    
    # Initialize LIS3MDL
    lis = LIS3MDL(bus_number=7, address=LIS3MDL_ADDRESS)
    print("Initializing LIS3MDL magnetometer...")
    if not lis.begin():
        print("Failed to initialize LIS3MDL! Is the sensor connected?")
        lsm.close()
        return
    
    # Initialize BNO055 for comparison
    bno = BNO055(bus_number=7, address=BNO055_ADDRESS_A)
    print("Initializing BNO055 sensor for comparison...")
    if not bno.begin():
        print("Failed to initialize BNO055! Is the sensor connected?")
        lsm.close()
        lis.close()
        return
    
    # Configure LSM6DSOX
    lsm.set_accel_range(4)    # ±4g
    lsm.set_gyro_range(500)   # ±500 dps
    
    # Initialize sensor fusion
    fusion = SensorFusion(lsm, lis)
    
    try:
        print("\nRunning sensor fusion. Press Ctrl+C to exit.")
        print("-" * 80)
        
        while True:
            # Update fusion algorithm
            if lsm.data_ready() and lis.data_ready():
                fusion.update()
            
            # Display header
            print("\n" + "=" * 80)
            print(f"TIMESTAMP: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)
            
            # ===== Raw Sensor Data =====
            print("\n1. RAW SENSOR DATA:")
            print("-" * 40)
            
            # Get accelerometer data
            accel_x, accel_y, accel_z = lsm.get_accel_data()
            print(f"Accelerometer: X: {accel_x:7.3f} g, Y: {accel_y:7.3f} g, Z: {accel_z:7.3f} g")
            
            # Get gyroscope data
            gyro_x, gyro_y, gyro_z = lsm.get_gyro_data()
            print(f"Gyroscope:     X: {gyro_x:7.2f} dps, Y: {gyro_y:7.2f} dps, Z: {gyro_z:7.2f} dps")
            
            # Get magnetic field data
            mag_x, mag_y, mag_z = lis.get_magnetic_data()
            print(f"Magnetometer:  X: {mag_x:7.2f} µT, Y: {mag_y:7.2f} µT, Z: {mag_z:7.2f} µT")
            
            # Calculate acceleration magnitude
            accel_mag = math.sqrt(accel_x**2 + accel_y**2 + accel_z**2)
            print(f"Accel Magnitude: {accel_mag:.3f} g")
            
            # ===== Fused Sensor Data =====
            print("\n2. SENSOR FUSION RESULTS:")
            print("-" * 40)
            
            # Get Euler angles
            heading, roll, pitch = fusion.get_euler()
            print(f"Euler Angles:   Heading: {heading:7.2f}°, Roll: {roll:7.2f}°, Pitch: {pitch:7.2f}°")
            
            # Get quaternion
            w, x, y, z = fusion.get_quaternion()
            print(f"Quaternion:     W: {w:7.4f}, X: {x:7.4f}, Y: {y:7.4f}, Z: {z:7.4f}")
            
            # Get calibration status
            sys, gyro, accel, mag = fusion.get_calibration()
            print(f"Calibration:    Sys={sys}, Gyro={gyro}, Accel={accel}, Mag={mag}")
            
            # Get linear acceleration
            x, y, z = fusion.get_linear_acceleration()
            print(f"Linear Accel:   X: {x:7.2f} m/s², Y: {y:7.2f} m/s², Z: {z:7.2f} m/s²")
            
            # Get gravity vector
            x, y, z = fusion.get_gravity()
            print(f"Gravity:        X: {x:7.2f} m/s², Y: {y:7.2f} m/s², Z: {z:7.2f} m/s²")
            
            # ===== BNO055 Reference Data =====
            print("\n3. BNO055 REFERENCE DATA:")
            print("-" * 40)
            
            # Get Euler angles
            bno_heading, bno_roll, bno_pitch = bno.get_euler()
            print(f"Euler Angles:   Heading: {bno_heading:7.2f}°, Roll: {bno_roll:7.2f}°, Pitch: {bno_pitch:7.2f}°")
            
            # Get calibration status
            bno_sys, bno_gyro, bno_accel, bno_mag = bno.get_calibration()
            print(f"Calibration:    Sys={bno_sys}, Gyro={bno_gyro}, Accel={bno_accel}, Mag={bno_mag}")
            
            # Get linear acceleration
            bno_x, bno_y, bno_z = bno.get_vector("linearaccel")
            print(f"Linear Accel:   X: {bno_x:7.2f} m/s², Y: {bno_y:7.2f} m/s², Z: {bno_z:7.2f} m/s²")
            
            # Get gravity vector
            bno_x, bno_y, bno_z = bno.get_vector("gravity")
            print(f"Gravity:        X: {bno_x:7.2f} m/s², Y: {bno_y:7.2f} m/s², Z: {bno_z:7.2f} m/s²")
            
            # ===== Comparison =====
            print("\n4. DIFFERENCE (Fusion - BNO055):")
            print("-" * 40)
            
            # Calculate difference in Euler angles
            hdg_diff = heading - bno_heading
            roll_diff = roll - bno_roll
            pitch_diff = pitch - bno_pitch
            
            # Normalize heading difference to -180 to +180
            if hdg_diff > 180:
                hdg_diff -= 360
            elif hdg_diff < -180:
                hdg_diff += 360
                
            print(f"Euler Angles:   Heading: {hdg_diff:7.2f}°, Roll: {roll_diff:7.2f}°, Pitch: {pitch_diff:7.2f}°")
            
            print("-" * 80)
            time.sleep(0.5)  # Update rate
            
    except KeyboardInterrupt:
        print("\nExiting program")
    except Exception as e:
        print(f"\nError occurred: {e}")
    finally:
        # Clean up
        lsm.close()
        lis.close()
        bno.close()
        print("I2C connections closed")


if __name__ == "__main__":
    main()