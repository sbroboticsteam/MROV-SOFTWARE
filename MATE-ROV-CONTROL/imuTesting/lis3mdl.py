from smbus2 import SMBus
import time
import math

# LIS3MDL Register addresses from the datasheet
LIS3MDL_ADDRESS = 0x1C  # Default I2C address (0x1E is alternative)

# Register addresses
LIS3MDL_WHO_AM_I = 0x0F
LIS3MDL_CTRL_REG1 = 0x20
LIS3MDL_CTRL_REG2 = 0x21
LIS3MDL_CTRL_REG3 = 0x22
LIS3MDL_CTRL_REG4 = 0x23
LIS3MDL_CTRL_REG5 = 0x24
LIS3MDL_STATUS_REG = 0x27
LIS3MDL_OUT_X_L = 0x28
LIS3MDL_OUT_X_H = 0x29
LIS3MDL_OUT_Y_L = 0x2A
LIS3MDL_OUT_Y_H = 0x2B
LIS3MDL_OUT_Z_L = 0x2C
LIS3MDL_OUT_Z_H = 0x2D
LIS3MDL_TEMP_OUT_L = 0x2E
LIS3MDL_TEMP_OUT_H = 0x2F
LIS3MDL_INT_CFG = 0x30
LIS3MDL_INT_SRC = 0x31
LIS3MDL_INT_THS_L = 0x32
LIS3MDL_INT_THS_H = 0x33

# Operation modes and settings
# CTRL_REG1 (0x20) options
LIS3MDL_TEMP_EN = 0x80      # Temperature sensor enable
LIS3MDL_OM_LOW = 0x00       # Low-power mode
LIS3MDL_OM_MEDIUM = 0x20    # Medium-performance mode
LIS3MDL_OM_HIGH = 0x40      # High-performance mode
LIS3MDL_OM_ULTRA = 0x60     # Ultra-high-performance mode
LIS3MDL_DO_0_625 = 0x00     # Output data rate: 0.625 Hz
LIS3MDL_DO_1_25 = 0x04      # Output data rate: 1.25 Hz
LIS3MDL_DO_2_5 = 0x08       # Output data rate: 2.5 Hz
LIS3MDL_DO_5 = 0x0C         # Output data rate: 5 Hz
LIS3MDL_DO_10 = 0x10        # Output data rate: 10 Hz
LIS3MDL_DO_20 = 0x14        # Output data rate: 20 Hz
LIS3MDL_DO_40 = 0x18        # Output data rate: 40 Hz
LIS3MDL_DO_80 = 0x1C        # Output data rate: 80 Hz
LIS3MDL_FAST_ODR = 0x02     # Enable fast ODR
LIS3MDL_ST = 0x01           # Self-test enable

# CTRL_REG2 (0x21) options
LIS3MDL_FS_4 = 0x00         # Full-scale ±4 gauss
LIS3MDL_FS_8 = 0x20         # Full-scale ±8 gauss
LIS3MDL_FS_12 = 0x40        # Full-scale ±12 gauss
LIS3MDL_FS_16 = 0x60        # Full-scale ±16 gauss
LIS3MDL_REBOOT = 0x08       # Reboot memory content
LIS3MDL_SOFT_RST = 0x04     # Configuration registers and user register reset function

# CTRL_REG3 (0x22) options
LIS3MDL_LP = 0x20           # Low-power mode
LIS3MDL_SIM = 0x04          # SPI mode selection
LIS3MDL_MD_CONTINUOUS = 0x00  # Continuous-conversion mode
LIS3MDL_MD_SINGLE = 0x01    # Single-conversion mode
LIS3MDL_MD_POWERDOWN = 0x03 # Power-down mode

# CTRL_REG4 (0x23) options
LIS3MDL_OMZ_LOW = 0x00      # Low-power mode for Z axis
LIS3MDL_OMZ_MEDIUM = 0x04   # Medium-performance mode for Z axis
LIS3MDL_OMZ_HIGH = 0x08     # High-performance mode for Z axis
LIS3MDL_OMZ_ULTRA = 0x0C    # Ultra-high-performance mode for Z axis
LIS3MDL_BLE = 0x02          # Big/Little Endian data selection

# Sensitivity values (LSB/gauss) for different full-scale settings
LIS3MDL_SENSITIVITY_4GAUSS = 6842  # LSB/gauss
LIS3MDL_SENSITIVITY_8GAUSS = 3421  # LSB/gauss
LIS3MDL_SENSITIVITY_12GAUSS = 2281  # LSB/gauss
LIS3MDL_SENSITIVITY_16GAUSS = 1711  # LSB/gauss


class LIS3MDL:
    def __init__(self, bus_number=7, address=LIS3MDL_ADDRESS):
        self.bus = SMBus(bus_number)
        self.address = address
        self.scale = LIS3MDL_FS_4  # Default scale
        self.sensitivity = LIS3MDL_SENSITIVITY_4GAUSS
        
    def begin(self):
        """Initialize the LIS3MDL sensor"""
        # Check if the sensor is responding
        chip_id = self._read_byte(LIS3MDL_WHO_AM_I)
        if chip_id != 0x3D:
            print(f"Wrong chip ID: {chip_id:02X}, expected 0x3D")
            return False
        
        # Reset the device
        self._write_byte(LIS3MDL_CTRL_REG2, LIS3MDL_SOFT_RST)
        time.sleep(0.010)  # Wait for reset to complete
        
        # Configure the device
        # CTRL_REG1: Ultra-high-performance mode for X and Y, 80 Hz ODR, Temperature sensor enabled
        self._write_byte(LIS3MDL_CTRL_REG1, LIS3MDL_TEMP_EN | LIS3MDL_OM_ULTRA | LIS3MDL_DO_80)
        
        # CTRL_REG2: ±4 gauss full-scale
        self._write_byte(LIS3MDL_CTRL_REG2, self.scale)
        
        # CTRL_REG3: Continuous-conversion mode
        self._write_byte(LIS3MDL_CTRL_REG3, LIS3MDL_MD_CONTINUOUS)
        
        # CTRL_REG4: Ultra-high-performance mode for Z axis, little endian data selection
        self._write_byte(LIS3MDL_CTRL_REG4, LIS3MDL_OMZ_ULTRA)
        
        # Set sensitivity based on scale
        self._update_sensitivity()
        
        return True
    
    def _update_sensitivity(self):
        """Update sensitivity based on current scale setting"""
        if self.scale == LIS3MDL_FS_4:
            self.sensitivity = LIS3MDL_SENSITIVITY_4GAUSS
        elif self.scale == LIS3MDL_FS_8:
            self.sensitivity = LIS3MDL_SENSITIVITY_8GAUSS
        elif self.scale == LIS3MDL_FS_12:
            self.sensitivity = LIS3MDL_SENSITIVITY_12GAUSS
        elif self.scale == LIS3MDL_FS_16:
            self.sensitivity = LIS3MDL_SENSITIVITY_16GAUSS
    
    def set_scale(self, scale):
        """Set the full-scale range
        
        Args:
            scale: One of LIS3MDL_FS_4, LIS3MDL_FS_8, LIS3MDL_FS_12, or LIS3MDL_FS_16
        """
        if scale not in [LIS3MDL_FS_4, LIS3MDL_FS_8, LIS3MDL_FS_12, LIS3MDL_FS_16]:
            return False
            
        self.scale = scale
        self._write_byte(LIS3MDL_CTRL_REG2, scale)
        self._update_sensitivity()
        return True
    
    def set_data_rate(self, data_rate):
        """Set the output data rate
        
        Args:
            data_rate: One of the LIS3MDL_DO_* constants
        """
        # Read current value of CTRL_REG1
        current = self._read_byte(LIS3MDL_CTRL_REG1)
        # Clear the data rate bits and set new rate
        new_value = (current & 0xE3) | data_rate
        self._write_byte(LIS3MDL_CTRL_REG1, new_value)
        return True
    
    def set_operation_mode(self, mode):
        """Set the operation mode
        
        Args:
            mode: One of LIS3MDL_MD_CONTINUOUS, LIS3MDL_MD_SINGLE, or LIS3MDL_MD_POWERDOWN
        """
        if mode not in [LIS3MDL_MD_CONTINUOUS, LIS3MDL_MD_SINGLE, LIS3MDL_MD_POWERDOWN]:
            return False
            
        # Read current value of CTRL_REG3
        current = self._read_byte(LIS3MDL_CTRL_REG3)
        # Clear the mode bits and set new mode
        new_value = (current & 0xFC) | mode
        self._write_byte(LIS3MDL_CTRL_REG3, new_value)
        return True
    
    def get_temp(self):
        """Get the temperature in Celsius"""
        # LIS3MDL doesn't provide temperature in Celsius directly
        # Reading raw temperature data
        temp_data = self._read_registers(LIS3MDL_TEMP_OUT_L, 2)
        temp_raw = self._convert_signed_short(temp_data[0] | (temp_data[1] << 8))
        
        # The datasheet doesn't provide a specific formula for temperature conversion
        # This is an approximate conversion based on other ST sensors
        # For more accurate readings, refer to the specific device documentation
        return 25.0 + temp_raw / 8.0  # Approximate conversion
    
    def data_ready(self):
        """Check if new magnetometer data is available"""
        status = self._read_byte(LIS3MDL_STATUS_REG)
        return (status & 0x08) != 0  # ZYXDA bit
    
    def get_magnetic_data(self):
        """Get the magnetometer data in micro-Tesla (µT)"""
        # Read the 6 data registers (X, Y, Z magnetic data)
        data = self._read_registers(LIS3MDL_OUT_X_L, 6)
        
        # Combine the high and low bytes to get the raw values
        x_raw = self._convert_signed_short(data[0] | (data[1] << 8))
        y_raw = self._convert_signed_short(data[2] | (data[3] << 8))
        z_raw = self._convert_signed_short(data[4] | (data[5] << 8))
        
        # Convert to micro-Tesla (µT)
        # According to datasheet: 1 gauss = 100 µT
        x = x_raw * 100.0 / self.sensitivity
        y = y_raw * 100.0 / self.sensitivity
        z = z_raw * 100.0 / self.sensitivity
        
        return (x, y, z)
    
    def get_heading(self):
        """Calculate the magnetic heading in degrees"""
        x, y, z = self.get_magnetic_data()
        heading = math.atan2(y, x) * 180.0 / math.pi
        
        # Normalize to 0-360
        if heading < 0:
            heading += 360.0
            
        return heading
    
    def get_magnitude(self):
        """Calculate the magnitude of the magnetic field in micro-Tesla (µT)"""
        x, y, z = self.get_magnetic_data()
        return math.sqrt(x*x + y*y + z*z)
    
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
    """Main function to initialize and read from the LIS3MDL sensor"""
    # Initialize the LIS3MDL sensor
    lis = LIS3MDL(bus_number=7, address=LIS3MDL_ADDRESS)
    
    print("Initializing LIS3MDL magnetometer sensor...")
    if not lis.begin():
        print("Failed to initialize LIS3MDL! Is the sensor connected?")
        return
    
    # Get chip ID
    chip_id = lis._read_byte(LIS3MDL_WHO_AM_I)
    print(f"\nLIS3MDL Chip ID: 0x{chip_id:02X} (should be 0x3D)")
    
    # Print scales and settings
    scales = {
        LIS3MDL_FS_4: "±4 gauss",
        LIS3MDL_FS_8: "±8 gauss",
        LIS3MDL_FS_12: "±12 gauss",
        LIS3MDL_FS_16: "±16 gauss"
    }
    current_scale = lis.scale
    print(f"Current scale setting: {scales.get(current_scale, 'Unknown')}")
    
    # Get current temperature
    temp = lis.get_temp()
    print(f"Current Temperature: {temp:.1f}°C")
    
    try:
        print("\nReading magnetometer data. Press Ctrl+C to exit.")
        while True:
            # Wait for data to be ready
            if lis.data_ready():
                # Get magnetic field data
                x, y, z = lis.get_magnetic_data()
                print(f"Magnetic Field - X: {x:8.2f} µT, Y: {y:8.2f} µT, Z: {z:8.2f} µT", end="")
                
                # Calculate heading
                heading = lis.get_heading()
                print(f"  Heading: {heading:6.1f}°", end="")
                
                # Calculate magnitude
                magnitude = lis.get_magnitude()
                print(f"  Magnitude: {magnitude:8.2f} µT")
            
            time.sleep(0.1)  # Delay between readings
            
    except KeyboardInterrupt:
        print("\nExiting program")
    finally:
        lis.close()
        print("I2C connection closed")


if __name__ == "__main__":
    main()