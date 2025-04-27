from smbus2 import SMBus
import time
import math
import struct

# LSM6DSOX Register addresses from the datasheet
LSM6DSOX_ADDRESS = 0x6A  # Default I2C address (0x6B is alternative)

# Register addresses
LSM6DSOX_WHO_AM_I = 0x0F        # Device ID register
LSM6DSOX_CTRL1_XL = 0x10        # Accelerometer control register 1
LSM6DSOX_CTRL2_G = 0x11         # Gyroscope control register
LSM6DSOX_CTRL3_C = 0x12         # Control register 3
LSM6DSOX_CTRL4_C = 0x13         # Control register 4
LSM6DSOX_CTRL5_C = 0x14         # Control register 5
LSM6DSOX_CTRL6_C = 0x15         # Control register 6
LSM6DSOX_CTRL7_G = 0x16         # Control register 7
LSM6DSOX_CTRL8_XL = 0x17        # Control register 8
LSM6DSOX_CTRL9_XL = 0x18        # Control register 9
LSM6DSOX_CTRL10_C = 0x19        # Control register 10
LSM6DSOX_STATUS_REG = 0x1E      # Status register

# Output data registers
LSM6DSOX_OUTX_L_G = 0x22        # Gyroscope X-axis output (low byte)
LSM6DSOX_OUTX_H_G = 0x23        # Gyroscope X-axis output (high byte)
LSM6DSOX_OUTY_L_G = 0x24        # Gyroscope Y-axis output (low byte)
LSM6DSOX_OUTY_H_G = 0x25        # Gyroscope Y-axis output (high byte)
LSM6DSOX_OUTZ_L_G = 0x26        # Gyroscope Z-axis output (low byte)
LSM6DSOX_OUTZ_H_G = 0x27        # Gyroscope Z-axis output (high byte)
LSM6DSOX_OUTX_L_A = 0x28        # Accelerometer X-axis output (low byte)
LSM6DSOX_OUTX_H_A = 0x29        # Accelerometer X-axis output (high byte)
LSM6DSOX_OUTY_L_A = 0x2A        # Accelerometer Y-axis output (low byte)
LSM6DSOX_OUTY_H_A = 0x2B        # Accelerometer Y-axis output (high byte)
LSM6DSOX_OUTZ_L_A = 0x2C        # Accelerometer Z-axis output (low byte)
LSM6DSOX_OUTZ_H_A = 0x2D        # Accelerometer Z-axis output (high byte)
LSM6DSOX_TEMP_L = 0x20          # Temperature output (low byte)
LSM6DSOX_TEMP_H = 0x21          # Temperature output (high byte)

# Accelerometer output data rate and scale
LSM6DSOX_XL_ODR_OFF = 0x00      # Power-down mode
LSM6DSOX_XL_ODR_12HZ5 = 0x10    # 12.5Hz
LSM6DSOX_XL_ODR_26HZ = 0x20     # 26Hz
LSM6DSOX_XL_ODR_52HZ = 0x30     # 52Hz
LSM6DSOX_XL_ODR_104HZ = 0x40    # 104Hz
LSM6DSOX_XL_ODR_208HZ = 0x50    # 208Hz
LSM6DSOX_XL_ODR_416HZ = 0x60    # 416Hz
LSM6DSOX_XL_ODR_833HZ = 0x70    # 833Hz
LSM6DSOX_XL_ODR_1666HZ = 0x80   # 1.66kHz
LSM6DSOX_XL_ODR_3333HZ = 0x90   # 3.33kHz
LSM6DSOX_XL_ODR_6667HZ = 0xA0   # 6.67kHz

LSM6DSOX_XL_FS_2G = 0x00        # ±2g full scale
LSM6DSOX_XL_FS_4G = 0x08        # ±4g full scale
LSM6DSOX_XL_FS_8G = 0x0C        # ±8g full scale
LSM6DSOX_XL_FS_16G = 0x04       # ±16g full scale

# Gyroscope output data rate and scale
LSM6DSOX_G_ODR_OFF = 0x00       # Power-down mode
LSM6DSOX_G_ODR_12HZ5 = 0x10     # 12.5Hz
LSM6DSOX_G_ODR_26HZ = 0x20      # 26Hz
LSM6DSOX_G_ODR_52HZ = 0x30      # 52Hz
LSM6DSOX_G_ODR_104HZ = 0x40     # 104Hz
LSM6DSOX_G_ODR_208HZ = 0x50     # 208Hz
LSM6DSOX_G_ODR_416HZ = 0x60     # 416Hz
LSM6DSOX_G_ODR_833HZ = 0x70     # 833Hz
LSM6DSOX_G_ODR_1666HZ = 0x80    # 1.66kHz
LSM6DSOX_G_ODR_3333HZ = 0x90    # 3.33kHz
LSM6DSOX_G_ODR_6667HZ = 0xA0    # 6.67kHz

LSM6DSOX_G_FS_125DPS = 0x02     # ±125 degrees per second
LSM6DSOX_G_FS_250DPS = 0x00     # ±250 degrees per second
LSM6DSOX_G_FS_500DPS = 0x04     # ±500 degrees per second
LSM6DSOX_G_FS_1000DPS = 0x08    # ±1000 degrees per second
LSM6DSOX_G_FS_2000DPS = 0x0C    # ±2000 degrees per second

class LSM6DSOX:
    def __init__(self, bus_number=7, address=LSM6DSOX_ADDRESS):
        self.bus = SMBus(bus_number)
        self.address = address
        
        # Default settings
        self.accel_scale = 2.0  # ±2g
        self.gyro_scale = 250.0  # ±250 dps
        
    def begin(self):
        """Initialize the LSM6DSOX sensor"""
        # Check if the sensor is responding
        chip_id = self._read_byte(LSM6DSOX_WHO_AM_I)
        if chip_id != 0x6C:  # 0x6C is the expected WHO_AM_I value
            print(f"Wrong chip ID: {chip_id:02X}, expected 0x6C")
            return False
        
        # Reset the device
        self._write_byte(LSM6DSOX_CTRL3_C, 0x01)  # Set SW_RESET bit
        time.sleep(0.1)  # Wait for reset to complete
        
        # Wait for the device to boot up
        while self._read_byte(LSM6DSOX_CTRL3_C) & 0x01:
            time.sleep(0.01)
        
        # Enable Block Data Update (BDU)
        self._write_byte(LSM6DSOX_CTRL3_C, 0x04)
        
        # Configure accelerometer: 208Hz, ±2g
        self._write_byte(LSM6DSOX_CTRL1_XL, LSM6DSOX_XL_ODR_208HZ | LSM6DSOX_XL_FS_2G)
        
        # Configure gyroscope: 208Hz, ±250dps
        self._write_byte(LSM6DSOX_CTRL2_G, LSM6DSOX_G_ODR_208HZ | LSM6DSOX_G_FS_250DPS)
        
        return True
    
    def set_accel_range(self, range_g):
        """Set accelerometer range in g"""
        if range_g == 2:
            self._write_byte(LSM6DSOX_CTRL1_XL, (self._read_byte(LSM6DSOX_CTRL1_XL) & ~0x0C) | LSM6DSOX_XL_FS_2G)
            self.accel_scale = 2.0
        elif range_g == 4:
            self._write_byte(LSM6DSOX_CTRL1_XL, (self._read_byte(LSM6DSOX_CTRL1_XL) & ~0x0C) | LSM6DSOX_XL_FS_4G)
            self.accel_scale = 4.0
        elif range_g == 8:
            self._write_byte(LSM6DSOX_CTRL1_XL, (self._read_byte(LSM6DSOX_CTRL1_XL) & ~0x0C) | LSM6DSOX_XL_FS_8G)
            self.accel_scale = 8.0
        elif range_g == 16:
            self._write_byte(LSM6DSOX_CTRL1_XL, (self._read_byte(LSM6DSOX_CTRL1_XL) & ~0x0C) | LSM6DSOX_XL_FS_16G)
            self.accel_scale = 16.0
        else:
            return False
        return True
    
    def set_gyro_range(self, range_dps):
        """Set gyroscope range in degrees per second"""
        if range_dps == 125:
            self._write_byte(LSM6DSOX_CTRL2_G, (self._read_byte(LSM6DSOX_CTRL2_G) & ~0x0C) | LSM6DSOX_G_FS_125DPS)
            self.gyro_scale = 125.0
        elif range_dps == 250:
            self._write_byte(LSM6DSOX_CTRL2_G, (self._read_byte(LSM6DSOX_CTRL2_G) & ~0x0C) | LSM6DSOX_G_FS_250DPS)
            self.gyro_scale = 250.0
        elif range_dps == 500:
            self._write_byte(LSM6DSOX_CTRL2_G, (self._read_byte(LSM6DSOX_CTRL2_G) & ~0x0C) | LSM6DSOX_G_FS_500DPS)
            self.gyro_scale = 500.0
        elif range_dps == 1000:
            self._write_byte(LSM6DSOX_CTRL2_G, (self._read_byte(LSM6DSOX_CTRL2_G) & ~0x0C) | LSM6DSOX_G_FS_1000DPS)
            self.gyro_scale = 1000.0
        elif range_dps == 2000:
            self._write_byte(LSM6DSOX_CTRL2_G, (self._read_byte(LSM6DSOX_CTRL2_G) & ~0x0C) | LSM6DSOX_G_FS_2000DPS)
            self.gyro_scale = 2000.0
        else:
            return False
        return True
    
    def get_accel_data(self):
        """Get accelerometer data in g"""
        # Read 6 bytes of accelerometer data (X, Y, Z) at once
        data = self._read_registers(LSM6DSOX_OUTX_L_A, 6)
        
        # Combine the high and low bytes to get the signed 16-bit values
        x = self._convert_signed_short(data[0] | (data[1] << 8))
        y = self._convert_signed_short(data[2] | (data[3] << 8))
        z = self._convert_signed_short(data[4] | (data[5] << 8))
        
        # Convert to g based on selected scale (±2g, ±4g, ±8g, ±16g)
        # Sensitivity in LSB/g from datasheet depends on selected scale
        sensitivity = 32768.0 / self.accel_scale
        
        x_g = x / sensitivity
        y_g = y / sensitivity
        z_g = z / sensitivity
        
        return (x_g, y_g, z_g)
    
    def get_gyro_data(self):
        """Get gyroscope data in degrees per second"""
        # Read 6 bytes of gyroscope data (X, Y, Z) at once
        data = self._read_registers(LSM6DSOX_OUTX_L_G, 6)
        
        # Combine the high and low bytes to get the signed 16-bit values
        x = self._convert_signed_short(data[0] | (data[1] << 8))
        y = self._convert_signed_short(data[2] | (data[3] << 8))
        z = self._convert_signed_short(data[4] | (data[5] << 8))
        
        # Convert to dps based on selected scale (±125, ±250, ±500, ±1000, ±2000 dps)
        # Sensitivity in LSB/dps from datasheet depends on selected scale
        sensitivity = 32768.0 / self.gyro_scale
        
        x_dps = x / sensitivity
        y_dps = y / sensitivity
        z_dps = z / sensitivity
        
        return (x_dps, y_dps, z_dps)
    
    def get_temp(self):
        """Get temperature in degrees Celsius"""
        # Read 2 bytes of temperature data
        data = self._read_registers(LSM6DSOX_TEMP_L, 2)
        
        # Combine the high and low bytes to get the signed 16-bit value
        temp_raw = self._convert_signed_short(data[0] | (data[1] << 8))
        
        # Convert to degrees Celsius
        # From datasheet: 0 LSB = 25°C, 1 LSB = 1/256 °C
        temp_c = 25.0 + temp_raw / 256.0
        
        return temp_c
    
    def data_ready(self):
        """Check if new data is available"""
        status = self._read_byte(LSM6DSOX_STATUS_REG)
        return (status & 0x03) == 0x03  # Check if both XLDA and GDA bits are set
    
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
    """Main function to initialize and read from the LSM6DSOX sensor"""
    # Initialize the LSM6DSOX sensor
    sensor = LSM6DSOX(bus_number=7, address=LSM6DSOX_ADDRESS)
    
    print("Initializing LSM6DSOX sensor...")
    if not sensor.begin():
        print("Failed to initialize LSM6DSOX! Is the sensor connected?")
        return
    
    # Get sensor ID
    sensor_id = sensor._read_byte(LSM6DSOX_WHO_AM_I)
    print(f"\nLSM6DSOX Sensor ID: 0x{sensor_id:02X}")
    
    # Set ranges for better precision
    sensor.set_accel_range(4)  # ±4g
    sensor.set_gyro_range(500)  # ±500 dps
    
    # Get current temperature
    temp = sensor.get_temp()
    print(f"\nCurrent Temperature: {temp:.2f}°C")
    
    try:
        print("\nReading sensor data. Press Ctrl+C to exit.")
        while True:
            # Wait for new data to be available
            if sensor.data_ready():
                # Get accelerometer data
                accel_x, accel_y, accel_z = sensor.get_accel_data()
                print(f"Accelerometer: X: {accel_x:7.3f} g, Y: {accel_y:7.3f} g, Z: {accel_z:7.3f} g")
                
                # Get gyroscope data
                gyro_x, gyro_y, gyro_z = sensor.get_gyro_data()
                print(f"Gyroscope:     X: {gyro_x:7.2f} dps, Y: {gyro_y:7.2f} dps, Z: {gyro_z:7.2f} dps")
                
                # Get temperature
                temp = sensor.get_temp()
                print(f"Temperature:   {temp:.2f}°C")
                
                # Calculate acceleration magnitude
                accel_mag = math.sqrt(accel_x**2 + accel_y**2 + accel_z**2)
                print(f"Accel Magnitude: {accel_mag:.3f} g")
                
                print("------------------------------------------------------")
            
            time.sleep(0.1)  # Delay between readings
            
    except KeyboardInterrupt:
        print("\nExiting program")
    finally:
        sensor.close()
        print("I2C connection closed")


if __name__ == "__main__":
    main()