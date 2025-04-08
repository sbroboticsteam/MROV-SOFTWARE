from smbus2 import SMBus
import time
import math
import struct

# BNO055 Register addresses from the datasheet
BNO055_ADDRESS_A = 0x28  # Default address
BNO055_ADDRESS_B = 0x29  # Alternative address

# Page 0 registers
BNO055_CHIP_ID = 0x00
BNO055_ACCEL_REV_ID = 0x01
BNO055_MAG_REV_ID = 0x02
BNO055_GYRO_REV_ID = 0x03
BNO055_SW_REV_ID_LSB = 0x04
BNO055_SW_REV_ID_MSB = 0x05
BNO055_BL_REV_ID = 0x06
BNO055_PAGE_ID = 0x07
BNO055_ACCEL_DATA_X_LSB = 0x08
BNO055_ACCEL_DATA_X_MSB = 0x09
BNO055_ACCEL_DATA_Y_LSB = 0x0A
BNO055_ACCEL_DATA_Y_MSB = 0x0B
BNO055_ACCEL_DATA_Z_LSB = 0x0C
BNO055_ACCEL_DATA_Z_MSB = 0x0D
BNO055_MAG_DATA_X_LSB = 0x0E
BNO055_MAG_DATA_X_MSB = 0x0F
BNO055_MAG_DATA_Y_LSB = 0x10
BNO055_MAG_DATA_Y_MSB = 0x11
BNO055_MAG_DATA_Z_LSB = 0x12
BNO055_MAG_DATA_Z_MSB = 0x13
BNO055_GYRO_DATA_X_LSB = 0x14
BNO055_GYRO_DATA_X_MSB = 0x15
BNO055_GYRO_DATA_Y_LSB = 0x16
BNO055_GYRO_DATA_Y_MSB = 0x17
BNO055_GYRO_DATA_Z_LSB = 0x18
BNO055_GYRO_DATA_Z_MSB = 0x19
BNO055_EULER_H_LSB = 0x1A  # Heading
BNO055_EULER_H_MSB = 0x1B
BNO055_EULER_R_LSB = 0x1C  # Roll
BNO055_EULER_R_MSB = 0x1D
BNO055_EULER_P_LSB = 0x1E  # Pitch
BNO055_EULER_P_MSB = 0x1F
BNO055_QUAT_W_LSB = 0x20  # Quaternion W
BNO055_QUAT_W_MSB = 0x21
BNO055_QUAT_X_LSB = 0x22  # Quaternion X
BNO055_QUAT_X_MSB = 0x23
BNO055_QUAT_Y_LSB = 0x24  # Quaternion Y
BNO055_QUAT_Y_MSB = 0x25
BNO055_QUAT_Z_LSB = 0x26  # Quaternion Z
BNO055_QUAT_Z_MSB = 0x27
BNO055_LINEAR_ACCEL_X_LSB = 0x28
BNO055_LINEAR_ACCEL_X_MSB = 0x29
BNO055_LINEAR_ACCEL_Y_LSB = 0x2A
BNO055_LINEAR_ACCEL_Y_MSB = 0x2B
BNO055_LINEAR_ACCEL_Z_LSB = 0x2C
BNO055_LINEAR_ACCEL_Z_MSB = 0x2D
BNO055_GRAVITY_X_LSB = 0x2E
BNO055_GRAVITY_X_MSB = 0x2F
BNO055_GRAVITY_Y_LSB = 0x30
BNO055_GRAVITY_Y_MSB = 0x31
BNO055_GRAVITY_Z_LSB = 0x32
BNO055_GRAVITY_Z_MSB = 0x33
BNO055_TEMP = 0x34
BNO055_CALIB_STAT = 0x35
BNO055_ST_RESULT = 0x36
BNO055_INT_STA = 0x37
BNO055_SYS_CLK_STATUS = 0x38
BNO055_SYS_STATUS = 0x39
BNO055_SYS_ERR = 0x3A
BNO055_UNIT_SEL = 0x3B
BNO055_OPR_MODE = 0x3D
BNO055_PWR_MODE = 0x3E
BNO055_SYS_TRIGGER = 0x3F
BNO055_TEMP_SOURCE = 0x40
BNO055_AXIS_MAP_CONFIG = 0x41
BNO055_AXIS_MAP_SIGN = 0x42

# Power modes
BNO055_POWER_MODE_NORMAL = 0x00
BNO055_POWER_MODE_LOWPOWER = 0x01
BNO055_POWER_MODE_SUSPEND = 0x02

# Operation modes
BNO055_OPERATION_MODE_CONFIG = 0x00
BNO055_OPERATION_MODE_ACCONLY = 0x01
BNO055_OPERATION_MODE_MAGONLY = 0x02
BNO055_OPERATION_MODE_GYRONLY = 0x03
BNO055_OPERATION_MODE_ACCMAG = 0x04
BNO055_OPERATION_MODE_ACCGYRO = 0x05
BNO055_OPERATION_MODE_MAGGYRO = 0x06
BNO055_OPERATION_MODE_AMG = 0x07
BNO055_OPERATION_MODE_IMUPLUS = 0x08
BNO055_OPERATION_MODE_COMPASS = 0x09
BNO055_OPERATION_MODE_M4G = 0x0A
BNO055_OPERATION_MODE_NDOF_FMC_OFF = 0x0B
BNO055_OPERATION_MODE_NDOF = 0x0C

class BNO055:
    def __init__(self, bus_number=7, address=BNO055_ADDRESS_A):
        self.bus = SMBus(bus_number)
        self.address = address
        
    def begin(self):
        """Initialize the BNO055 sensor"""
        # Check if the sensor is responding
        chip_id = self._read_byte(BNO055_CHIP_ID)
        if chip_id != 0xA0:
            print(f"Wrong chip ID: {chip_id:02X}, expected 0xA0")
            return False
        
        # Reset the device
        self._write_byte(BNO055_SYS_TRIGGER, 0x20)
        time.sleep(0.65)  # Wait for reset to complete
        
        # Make sure we're in config mode
        self._write_byte(BNO055_OPR_MODE, BNO055_OPERATION_MODE_CONFIG)
        time.sleep(0.02)
        
        # Set to normal power mode
        self._write_byte(BNO055_PWR_MODE, BNO055_POWER_MODE_NORMAL)
        time.sleep(0.01)
        
        # Configure the device
        # Use external crystal for better accuracy
        self._write_byte(BNO055_SYS_TRIGGER, 0x80)
        time.sleep(0.01)
        
        # Set to NDOF mode (fusion)
        self._write_byte(BNO055_OPR_MODE, BNO055_OPERATION_MODE_NDOF)
        time.sleep(0.02)  # Wait for mode switch
        
        return True
    
    def get_temp(self):
        """Get the temperature in Celsius"""
        return self._read_byte(BNO055_TEMP)
    
    def get_revision(self):
        """Get revision information for the sensor components"""
        accel_rev = self._read_byte(BNO055_ACCEL_REV_ID)
        mag_rev = self._read_byte(BNO055_MAG_REV_ID)
        gyro_rev = self._read_byte(BNO055_GYRO_REV_ID)
        sw_rev = (self._read_byte(BNO055_SW_REV_ID_MSB) << 8) | self._read_byte(BNO055_SW_REV_ID_LSB)
        bl_rev = self._read_byte(BNO055_BL_REV_ID)
        return {
            'accel': accel_rev,
            'mag': mag_rev,
            'gyro': gyro_rev,
            'sw': sw_rev,
            'bootloader': bl_rev
        }
    
    def get_calibration(self):
        """Get calibration status"""
        calib_stat = self._read_byte(BNO055_CALIB_STAT)
        sys = (calib_stat >> 6) & 0x03
        gyro = (calib_stat >> 4) & 0x03
        accel = (calib_stat >> 2) & 0x03
        mag = calib_stat & 0x03
        return (sys, gyro, accel, mag)
    
    def get_quaternion(self):
        """Get quaternion values"""
        quat_data = self._read_registers(BNO055_QUAT_W_LSB, 8)
        w = self._convert_signed_short(quat_data[0] | (quat_data[1] << 8)) / 16384.0
        x = self._convert_signed_short(quat_data[2] | (quat_data[3] << 8)) / 16384.0
        y = self._convert_signed_short(quat_data[4] | (quat_data[5] << 8)) / 16384.0
        z = self._convert_signed_short(quat_data[6] | (quat_data[7] << 8)) / 16384.0
        return (w, x, y, z)
    
    def get_euler(self):
        """Get Euler angles (heading/yaw, roll, pitch) in degrees"""
        euler_data = self._read_registers(BNO055_EULER_H_LSB, 6)
        heading = self._convert_signed_short(euler_data[0] | (euler_data[1] << 8)) / 16.0
        roll = self._convert_signed_short(euler_data[2] | (euler_data[3] << 8)) / 16.0
        pitch = self._convert_signed_short(euler_data[4] | (euler_data[5] << 8)) / 16.0
        return (heading, roll, pitch)
    
    def get_vector(self, vector_type):
        """Get different vector data from the sensor"""
        if vector_type == "accelerometer":
            base_reg = BNO055_ACCEL_DATA_X_LSB
        elif vector_type == "magnetometer":
            base_reg = BNO055_MAG_DATA_X_LSB
        elif vector_type == "gyroscope":
            base_reg = BNO055_GYRO_DATA_X_LSB
        elif vector_type == "euler":
            base_reg = BNO055_EULER_H_LSB
        elif vector_type == "linearaccel":
            base_reg = BNO055_LINEAR_ACCEL_X_LSB
        elif vector_type == "gravity":
            base_reg = BNO055_GRAVITY_X_LSB
        else:
            return None
        
        vector_data = self._read_registers(base_reg, 6)
        x = self._convert_signed_short(vector_data[0] | (vector_data[1] << 8))
        y = self._convert_signed_short(vector_data[2] | (vector_data[3] << 8))
        z = self._convert_signed_short(vector_data[4] | (vector_data[5] << 8))
        
        # Apply scaling based on vector type
        if vector_type == "accelerometer" or vector_type == "linearaccel" or vector_type == "gravity":
            # Accelerometer: 1m/s^2 = 100 LSB
            x /= 100.0
            y /= 100.0
            z /= 100.0
        elif vector_type == "magnetometer":
            # Magnetometer: 1uT = 16 LSB
            x /= 16.0
            y /= 16.0
            z /= 16.0
        elif vector_type == "gyroscope":
            # Gyroscope: 1rps = 900 LSB (or 1 deg/s = 16 LSB)
            x /= 16.0
            y /= 16.0
            z /= 16.0
        elif vector_type == "euler":
            # Euler: 1 degree = 16 LSB
            x /= 16.0
            y /= 16.0
            z /= 16.0
            
        return (x, y, z)
    
    def _read_byte(self, register):
        """Read a single byte from the specified register"""
        try:
            return self.bus.read_byte_data(self.address, register)
        except IOError as e:
            print(f"I/O error reading from register {register:02X}: {e}")
            return 0
    
    def _write_byte(self, register, value):
        """Write a single byte to the specified register"""
        try:
            self.bus.write_byte_data(self.address, register, value)
            return True
        except IOError as e:
            print(f"I/O error writing to register {register:02X}: {e}")
            return False
    
    def _read_registers(self, register, length):
        """Read multiple registers starting from the specified address"""
        try:
            return self.bus.read_i2c_block_data(self.address, register, length)
        except IOError as e:
            print(f"I/O error reading block from register {register:02X}: {e}")
            return [0] * length
    
    def _convert_signed_short(self, value):
        """Convert a 16-bit signed value"""
        if value >= 0x8000:
            return -((65535 - value) + 1)
        else:
            return value
            
    def close(self):
        """Close the I2C bus"""
        try:
            self.bus.close()
        except:
            pass


def main():
    """Main function to initialize and read from the BNO055 sensor"""
    # Initialize the BNO055 sensor
    bno = BNO055(bus_number=7, address=BNO055_ADDRESS_A)
    
    print("Initializing BNO055 sensor...")
    if not bno.begin():
        print("Failed to initialize BNO055! Is the sensor connected?")
        return
    
    # Get sensor revision information
    rev_info = bno.get_revision()
    print("\nBNO055 Revision Information:")
    print(f"Accelerometer Rev: {rev_info['accel']}")
    print(f"Magnetometer Rev: {rev_info['mag']}")
    print(f"Gyroscope Rev: {rev_info['gyro']}")
    print(f"Software Rev: {rev_info['sw']}")
    print(f"Bootloader Rev: {rev_info['bootloader']}")
    
    # Get current temperature
    temp = bno.get_temp()
    print(f"\nCurrent Temperature: {temp}°C")
    
    print("\nCalibration status values: 0=uncalibrated, 3=fully calibrated")
    
    try:
        print("\nReading sensor data. Press Ctrl+C to exit.")
        while True:
            # Get Euler angles
            heading, roll, pitch = bno.get_euler()
            print(f"Euler Angles - Heading: {heading:7.2f}°, Roll: {roll:7.2f}°, Pitch: {pitch:7.2f}°  ", end="")
            
            # Get quaternion
            w, x, y, z = bno.get_quaternion()
            print(f"\t Quaternion - W: {w:6.4f}, X: {x:6.4f}, Y: {y:6.4f}, Z: {z:6.4f}  ", end="")
            
            # Get calibration status
            sys, gyro, accel, mag = bno.get_calibration()
            print(f"\t CALIBRATION: Sys={sys}, Gyro={gyro}, Accel={accel}, Mag={mag}")
            
            # Get accelerometer data
            x, y, z = bno.get_vector("accelerometer")
            print(f"Accelerometer - X: {x:7.2f} m/s², Y: {y:7.2f} m/s², Z: {z:7.2f} m/s²")
            
            # Get gyroscope data
            x, y, z = bno.get_vector("gyroscope")
            print(f"Gyroscope     - X: {x:7.2f} deg/s, Y: {y:7.2f} deg/s, Z: {z:7.2f} deg/s")
            
            # Get magnetometer data
            x, y, z = bno.get_vector("magnetometer")
            print(f"Magnetometer  - X: {x:7.2f} µT, Y: {y:7.2f} µT, Z: {z:7.2f} µT")
            
            # Get linear acceleration
            x, y, z = bno.get_vector("linearaccel")
            print(f"Linear Accel  - X: {x:7.2f} m/s², Y: {y:7.2f} m/s², Z: {z:7.2f} m/s²")
            
            # Get gravity vector
            x, y, z = bno.get_vector("gravity")
            print(f"Gravity       - X: {x:7.2f} m/s², Y: {y:7.2f} m/s², Z: {z:7.2f} m/s²")
            
            print("------------------------------------------------------")
            time.sleep(0.1)  # Delay between readings
            
    except KeyboardInterrupt:
        print("\nExiting program")
    finally:
        bno.close()
        print("I2C connection closed")


if __name__ == "__main__":
    main()