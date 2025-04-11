from smbus2 import SMBus
import time
import struct
import math

# IMU Addresses
BNO055_ADDRESS = 0x28
LSM6DOS_ADDRESS = 0x6A
LIS3MDL_ADDRESS = 0x1C  # Address stays the same

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

# LSM6DOS Registers
LSM6DOS_WHO_AM_I = 0x0F
LSM6DOS_CTRL1_XL = 0x10  # Accelerometer control register
LSM6DOS_CTRL2_G = 0x11   # Gyroscope control register
LSM6DOS_OUTX_L_G = 0x22  # Gyro data start
LSM6DOS_OUTX_L_XL = 0x28 # Accel data start

LIS3MDL_WHO_AM_I = 0x0F  # Correct for LIS3MDL
LIS3MDL_CTRL_REG1 = 0x20 # Control register 1
LIS3MDL_CTRL_REG2 = 0x21 # Control register 2
LIS3MDL_CTRL_REG3 = 0x22 # Control register 3
LIS3MDL_CTRL_REG4 = 0x23 # Control register 4
LIS3MDL_OUT_X_L = 0x28   # Output X LSB

class IMUSensor:
    def __init__(self, bus_number=7):
        self.bus = SMBus(bus_number)
        self.initialize_sensors()
        
    def initialize_sensors(self):
        # Try to initialize BNO055
        try:
            # Check BNO055 chip ID
            chip_id = self.bus.read_byte_data(BNO055_ADDRESS, BNO055_CHIP_ID)
            if chip_id == 0xA0:
                print(f"BNO055 detected with chip ID: 0x{chip_id:02X}")
                
                # Reset BNO055
                self.bus.write_byte_data(BNO055_ADDRESS, BNO055_SYS_TRIGGER, 0x20)
                time.sleep(0.65)  # Wait for reset
                
                # Set to config mode
                self.bus.write_byte_data(BNO055_ADDRESS, BNO055_OPR_MODE, 0x00)
                time.sleep(0.05)
                
                # Set to normal power mode
                self.bus.write_byte_data(BNO055_ADDRESS, BNO055_PWR_MODE, 0x00)
                time.sleep(0.01)
                
                # Set to page 0
                self.bus.write_byte_data(BNO055_ADDRESS, BNO055_PAGE_ID, 0x00)
                time.sleep(0.01)
                
                # Set to NDOF mode (fusion)
                self.bus.write_byte_data(BNO055_ADDRESS, BNO055_OPR_MODE, 0x0C)
                time.sleep(0.02)
                
                self.bno055_available = True
                print("BNO055 initialized successfully")
            else:
                print(f"Unexpected BNO055 chip ID: 0x{chip_id:02X}")
                self.bno055_available = False
        except Exception as e:
            print(f"BNO055 initialization failed: {e}")
            self.bno055_available = False
        
        # Try to initialize LSM6DOS (Accelerometer/Gyro)
        try:
            # Check LSM6DOS ID
            who_am_i = self.bus.read_byte_data(LSM6DOS_ADDRESS, LSM6DOS_WHO_AM_I)
            if who_am_i == 0x6C:  # This might vary, check datasheet
                print(f"LSM6DOS detected with ID: 0x{who_am_i:02X}")
                
                # Configure accelerometer: 2g range, 104 Hz
                self.bus.write_byte_data(LSM6DOS_ADDRESS, LSM6DOS_CTRL1_XL, 0x40)
                
                # Configure gyroscope: 2000 dps, 104 Hz
                self.bus.write_byte_data(LSM6DOS_ADDRESS, LSM6DOS_CTRL2_G, 0x4C)
                
                self.lsm6dos_available = True
                print("LSM6DOS initialized successfully")
            else:
                print(f"Unexpected LSM6DOS ID: 0x{who_am_i:02X}")
                self.lsm6dos_available = False
        except Exception as e:
            print(f"LSM6DOS initialization failed: {e}")
            self.lsm6dos_available = False
        
        # Try to initialize LIS3MDL (Magnetometer) - Updated for LIS3MDL
        try:
            # Check LIS3MDL ID
            who_am_i = self.bus.read_byte_data(LIS3MDL_ADDRESS, LIS3MDL_WHO_AM_I)
            if who_am_i == 0x3D:  # LIS3MDL correct chip ID
                print(f"LIS3MDL detected with ID: 0x{who_am_i:02X}")
                
                # Configure magnetometer for LIS3MDL
                # CTRL_REG1: Ultra-high-performance mode for X and Y, 80Hz data rate
                self.bus.write_byte_data(LIS3MDL_ADDRESS, LIS3MDL_CTRL_REG1, 0x72)
                
                # CTRL_REG2: ±4 gauss full scale
                self.bus.write_byte_data(LIS3MDL_ADDRESS, LIS3MDL_CTRL_REG2, 0x00)
                
                # CTRL_REG3: Continuous conversion mode
                self.bus.write_byte_data(LIS3MDL_ADDRESS, LIS3MDL_CTRL_REG3, 0x00)
                
                # CTRL_REG4: Ultra-high-performance mode for Z, little endian data
                self.bus.write_byte_data(LIS3MDL_ADDRESS, LIS3MDL_CTRL_REG4, 0x0C)
                
                self.lis3mdl_available = True
                print("LIS3MDL initialized successfully")
            else:
                print(f"Unexpected LIS3MDL ID: 0x{who_am_i:02X}")
                self.lis3mdl_available = False
        except Exception as e:
            print(f"LIS3MDL initialization failed: {e}")
            self.lis3mdl_available = False
            
    def read_bno055_data(self):
        if not self.bno055_available:
            return None
            
        data = {
            'accel': {'x': 0, 'y': 0, 'z': 0},
            'gyro': {'x': 0, 'y': 0, 'z': 0},
            'mag': {'x': 0, 'y': 0, 'z': 0},
            'euler': {'heading': 0, 'roll': 0, 'pitch': 0},
            'quaternion': {'w': 0, 'x': 0, 'y': 0, 'z': 0}
        }
        
        # Read accelerometer data (2 bytes each for x, y, z)
        accel_data = self.bus.read_i2c_block_data(BNO055_ADDRESS, BNO055_ACCEL_DATA, 6)
        data['accel']['x'] = struct.unpack('<h', bytes(accel_data[0:2]))[0] / 100.0  # m/s²
        data['accel']['y'] = struct.unpack('<h', bytes(accel_data[2:4]))[0] / 100.0
        data['accel']['z'] = struct.unpack('<h', bytes(accel_data[4:6]))[0] / 100.0
        
        # Read gyroscope data (2 bytes each for x, y, z)
        gyro_data = self.bus.read_i2c_block_data(BNO055_ADDRESS, BNO055_GYRO_DATA, 6)
        data['gyro']['x'] = struct.unpack('<h', bytes(gyro_data[0:2]))[0] / 16.0  # deg/s
        data['gyro']['y'] = struct.unpack('<h', bytes(gyro_data[2:4]))[0] / 16.0
        data['gyro']['z'] = struct.unpack('<h', bytes(gyro_data[4:6]))[0] / 16.0
        
        # Read magnetometer data (2 bytes each for x, y, z)
        mag_data = self.bus.read_i2c_block_data(BNO055_ADDRESS, BNO055_MAG_DATA, 6)
        data['mag']['x'] = struct.unpack('<h', bytes(mag_data[0:2]))[0] / 16.0  # µT
        data['mag']['y'] = struct.unpack('<h', bytes(mag_data[2:4]))[0] / 16.0
        data['mag']['z'] = struct.unpack('<h', bytes(mag_data[4:6]))[0] / 16.0
        
        # Read Euler angles data (2 bytes each for heading, roll, pitch)
        euler_data = self.bus.read_i2c_block_data(BNO055_ADDRESS, BNO055_EULER_DATA, 6)
        data['euler']['heading'] = struct.unpack('<h', bytes(euler_data[0:2]))[0] / 16.0  # degrees
        data['euler']['roll'] = struct.unpack('<h', bytes(euler_data[2:4]))[0] / 16.0
        data['euler']['pitch'] = struct.unpack('<h', bytes(euler_data[4:6]))[0] / 16.0
        
        # Read quaternion data (2 bytes each for w, x, y, z)
        quat_data = self.bus.read_i2c_block_data(BNO055_ADDRESS, BNO055_QUATERNION_DATA, 8)
        data['quaternion']['w'] = struct.unpack('<h', bytes(quat_data[0:2]))[0] / 16384.0
        data['quaternion']['x'] = struct.unpack('<h', bytes(quat_data[2:4]))[0] / 16384.0
        data['quaternion']['y'] = struct.unpack('<h', bytes(quat_data[4:6]))[0] / 16384.0
        data['quaternion']['z'] = struct.unpack('<h', bytes(quat_data[6:8]))[0] / 16384.0
        
        return data
    
    def read_lsm6dos_data(self):
        if not self.lsm6dos_available:
            return None
            
        data = {
            'accel': {'x': 0, 'y': 0, 'z': 0},
            'gyro': {'x': 0, 'y': 0, 'z': 0}
        }
        
        # Read accelerometer data (2 bytes each for x, y, z)
        accel_data = self.bus.read_i2c_block_data(LSM6DOS_ADDRESS, LSM6DOS_OUTX_L_XL, 6)
        data['accel']['x'] = struct.unpack('<h', bytes(accel_data[0:2]))[0] * 0.061 / 1000.0  # g to m/s²
        data['accel']['y'] = struct.unpack('<h', bytes(accel_data[2:4]))[0] * 0.061 / 1000.0
        data['accel']['z'] = struct.unpack('<h', bytes(accel_data[4:6]))[0] * 0.061 / 1000.0
        
        # Read gyroscope data (2 bytes each for x, y, z)
        gyro_data = self.bus.read_i2c_block_data(LSM6DOS_ADDRESS, LSM6DOS_OUTX_L_G, 6)
        data['gyro']['x'] = struct.unpack('<h', bytes(gyro_data[0:2]))[0] * 70.0 / 1000.0  # mdps to deg/s
        data['gyro']['y'] = struct.unpack('<h', bytes(gyro_data[2:4]))[0] * 70.0 / 1000.0
        data['gyro']['z'] = struct.unpack('<h', bytes(gyro_data[4:6]))[0] * 70.0 / 1000.0
        
        return data
    
    def read_lis3mdl_data(self):
        if not self.lis3mdl_available:
            return None
            
        data = {
            'mag': {'x': 0, 'y': 0, 'z': 0}
        }
        
        # Read magnetometer data (2 bytes each for x, y, z) - Updated for LIS3MDL
        mag_data = self.bus.read_i2c_block_data(LIS3MDL_ADDRESS, LIS3MDL_OUT_X_L, 6)
        # LIS3MDL with ±4 gauss range has a different scaling factor: 1/6842 gauss/LSB
        scaling_factor = 0.146  # µT per LSB (for ±4 gauss)
        data['mag']['x'] = struct.unpack('<h', bytes(mag_data[0:2]))[0] * scaling_factor
        data['mag']['y'] = struct.unpack('<h', bytes(mag_data[2:4]))[0] * scaling_factor
        data['mag']['z'] = struct.unpack('<h', bytes(mag_data[4:6]))[0] * scaling_factor
        
        return data
    
    def read_all_data(self):
        result = {}
        
        # BNO055 data
        bno055_data = self.read_bno055_data()
        if bno055_data:
            result['bno055'] = bno055_data
        
        # 9DOF Fusion board data
        lsm6dos_data = self.read_lsm6dos_data()
        if lsm6dos_data:
            result['lsm6dos'] = lsm6dos_data
        
        lis3mdl_data = self.read_lis3mdl_data()
        if lis3mdl_data:
            result['lis3mdl'] = lis3mdl_data
        
        return result
    
    def close(self):
        self.bus.close()

def main():
    # Initialize the IMU sensor
    imu = IMUSensor(bus_number=7)
    
    try:
        # Read and print IMU data continuously
        print("Reading IMU data... Press Ctrl+C to exit")
        while True:
            data = imu.read_all_data()
            
            # Print BNO055 data if available
            if 'bno055' in data:
                print("\n=== BNO055 Data ===")
                bno = data['bno055']
                print(f"Accel (m/s²): X={bno['accel']['x']:.2f}, Y={bno['accel']['y']:.2f}, Z={bno['accel']['z']:.2f}")
                print(f"Gyro (deg/s): X={bno['gyro']['x']:.2f}, Y={bno['gyro']['y']:.2f}, Z={bno['gyro']['z']:.2f}")
                print(f"Mag (µT): X={bno['mag']['x']:.2f}, Y={bno['mag']['y']:.2f}, Z={bno['mag']['z']:.2f}")
                print(f"Euler (deg): Heading={bno['euler']['heading']:.2f}, Roll={bno['euler']['roll']:.2f}, Pitch={bno['euler']['pitch']:.2f}")
                print(f"Quaternion: W={bno['quaternion']['w']:.4f}, X={bno['quaternion']['x']:.4f}, Y={bno['quaternion']['y']:.4f}, Z={bno['quaternion']['z']:.4f}")
            
            # Print LSM6DOS data if available
            if 'lsm6dos' in data:
                print("\n=== LSM6DOS Data ===")
                lsm = data['lsm6dos']
                print(f"Accel (m/s²): X={lsm['accel']['x']:.2f}, Y={lsm['accel']['y']:.2f}, Z={lsm['accel']['z']:.2f}")
                print(f"Gyro (deg/s): X={lsm['gyro']['x']:.2f}, Y={lsm['gyro']['y']:.2f}, Z={lsm['gyro']['z']:.2f}")
            
            # Print LIS3MDL data if available
            if 'lis3mdl' in data:
                print("\n=== LIS3MDL Data ===")
                lis = data['lis3mdl']
                print(f"Mag (µT): X={lis['mag']['x']:.2f}, Y={lis['mag']['y']:.2f}, Z={lis['mag']['z']:.2f}")
            
            time.sleep(0.5)  # Update every 0.5 seconds
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        imu.close()
        print("IMU connection closed")

if __name__ == "__main__":
    main()