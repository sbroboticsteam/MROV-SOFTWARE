#!/usr/bin/env python3
import time
import math
from lsm6dsox import LSM6DSOX, LSM6DSOX_ADDRESS
from lis3mdl import LIS3MDL, LIS3MDL_ADDRESS
from bno055 import BNO055, BNO055_ADDRESS_A

def main():
    """Initialize and read from all three IMU sensors simultaneously"""
    # Initialize the sensors
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
    
    # Initialize BNO055
    bno = BNO055(bus_number=7, address=BNO055_ADDRESS_A)
    print("Initializing BNO055 sensor...")
    if not bno.begin():
        print("Failed to initialize BNO055! Is the sensor connected?")
        lsm.close()
        lis.close()
        return
    
    # Configure LSM6DSOX
    lsm.set_accel_range(4)    # ±4g
    lsm.set_gyro_range(500)   # ±500 dps
    
    # Get sensor IDs
    lsm_id = lsm._read_byte(0x0F)  # LSM6DSOX_WHO_AM_I
    lis_id = lis._read_byte(0x0F)  # LIS3MDL_WHO_AM_I
    bno_id = bno._read_byte(0x00)  # BNO055_CHIP_ID
    
    print(f"\nSensor IDs - LSM6DSOX: 0x{lsm_id:02X}, LIS3MDL: 0x{lis_id:02X}, BNO055: 0x{bno_id:02X}")
    print("-" * 80)
    
    try:
        print("\nReading from all sensors. Press Ctrl+C to exit.")
        print("-" * 80)
        
        while True:
            # Display header
            print("\n" + "=" * 80)
            print(f"TIMESTAMP: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)
            
            # ===== LSM6DSOX Data =====
            print("\n1. LSM6DSOX SENSOR DATA:")
            print("-" * 40)
            
            # Only process LSM6DSOX data if it's ready
            if lsm.data_ready():
                # Get accelerometer data
                accel_x, accel_y, accel_z = lsm.get_accel_data()
                print(f"Accelerometer: X: {accel_x:7.3f} g, Y: {accel_y:7.3f} g, Z: {accel_z:7.3f} g")
                
                # Get gyroscope data
                gyro_x, gyro_y, gyro_z = lsm.get_gyro_data()
                print(f"Gyroscope:     X: {gyro_x:7.2f} dps, Y: {gyro_y:7.2f} dps, Z: {gyro_z:7.2f} dps")
                
                # Get temperature
                lsm_temp = lsm.get_temp()
                print(f"Temperature:   {lsm_temp:.2f}°C")
                
                # Calculate acceleration magnitude
                accel_mag = math.sqrt(accel_x**2 + accel_y**2 + accel_z**2)
                print(f"Accel Magnitude: {accel_mag:.3f} g")
            else:
                print("Waiting for LSM6DSOX data...")
            
            # ===== LIS3MDL Data =====
            print("\n2. LIS3MDL MAGNETOMETER DATA:")
            print("-" * 40)
            
            if lis.data_ready():
                # Get magnetic field data
                mag_x, mag_y, mag_z = lis.get_magnetic_data()
                print(f"Magnetic Field: X: {mag_x:7.2f} µT, Y: {mag_y:7.2f} µT, Z: {mag_z:7.2f} µT")
                
                # Calculate heading
                heading = lis.get_heading()
                print(f"Heading:        {heading:7.2f}°")
                
                # Calculate magnitude
                magnitude = lis.get_magnitude()
                print(f"Field Magnitude: {magnitude:7.2f} µT")
                
                # Get temperature
                lis_temp = lis.get_temp()
                print(f"Temperature:     {lis_temp:.1f}°C")
            else:
                print("Waiting for LIS3MDL data...")
            
            # ===== BNO055 Data =====
            print("\n3. BNO055 SENSOR DATA:")
            print("-" * 40)
            
            # Get Euler angles
            heading, roll, pitch = bno.get_euler()
            print(f"Euler Angles:   Heading: {heading:7.2f}°, Roll: {roll:7.2f}°, Pitch: {pitch:7.2f}°")
            
            # Get quaternion
            w, x, y, z = bno.get_quaternion()
            print(f"Quaternion:     W: {w:7.4f}, X: {x:7.4f}, Y: {y:7.4f}, Z: {z:7.4f}")
            
            # Get calibration status
            sys, gyro, accel, mag = bno.get_calibration()
            print(f"Calibration:    Sys={sys}, Gyro={gyro}, Accel={accel}, Mag={mag}")
            
            # Get accelerometer data
            x, y, z = bno.get_vector("accelerometer")
            print(f"Accelerometer:  X: {x:7.2f} m/s², Y: {y:7.2f} m/s², Z: {z:7.2f} m/s²")
            
            # Get gyroscope data
            x, y, z = bno.get_vector("gyroscope")
            print(f"Gyroscope:      X: {x:7.2f} deg/s, Y: {y:7.2f} deg/s, Z: {z:7.2f} deg/s")
            
            # Get magnetometer data
            x, y, z = bno.get_vector("magnetometer")
            print(f"Magnetometer:   X: {x:7.2f} µT, Y: {y:7.2f} µT, Z: {z:7.2f} µT")
            
            # Get linear acceleration
            x, y, z = bno.get_vector("linearaccel")
            print(f"Linear Accel:   X: {x:7.2f} m/s², Y: {y:7.2f} m/s², Z: {z:7.2f} m/s²")
            
            # Get gravity vector
            x, y, z = bno.get_vector("gravity")
            print(f"Gravity:        X: {x:7.2f} m/s², Y: {y:7.2f} m/s², Z: {z:7.2f} m/s²")
            
            # Get BNO055 temperature
            bno_temp = bno.get_temp()
            print(f"Temperature:    {bno_temp}°C")
            
            print("-" * 80)
            time.sleep(1.0)  # Slower update rate for readability
            
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