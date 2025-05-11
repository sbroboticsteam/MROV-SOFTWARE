import time
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger("ROV")

# Import the MS5837 sensor class with error handling
try:
    from rov.hardware.ms5837 import MS5837, MS5837_02BA, OSR_8192, DENSITY_SALTWATER
    MS5837_AVAILABLE = True
    logger.info("MS5837 module successfully imported")
except ImportError:
    try:
        from hardware.ms5837 import MS5837, MS5837_02BA, OSR_8192, DENSITY_SALTWATER
        MS5837_AVAILABLE = True
        logger.info("MS5837 module successfully imported")
    except ImportError:
        MS5837_AVAILABLE = False
        logger.warning("Could not import MS5837 class. Depth sensor functionality will be limited.")
        # Create dummy classes and constants for type checking
        class MS5837:
            pass
        class MS5837_02BA:
            pass
        OSR_8192 = 5
        DENSITY_SALTWATER = 1029

class DepthSensor:
    """Interface for the MS5837 depth sensor with velocity calculation."""
    
    def __init__(self, bus_number: int = 1):
        """Initialize the depth sensor.
        
        Args:
            bus_number: I2C bus number
        """
        self.sensor = None
        self.available = False
        
        # Data storage
        self.last_depth = 0.0
        self.last_pressure = 0.0
        self.last_temperature = 0.0
        self.initial_depth = 0.0
        self.relative_depth = 0.0
        
        # For rate limiting
        self.last_read_time = 0
        self.read_interval = 0.05  # 20Hz maximum reading rate
        
        # For velocity calculations
        self.previous_depth = 0.0
        self.previous_time = time.time()
        self.current_velocity = 0.0
        
        # Flags and settings
        self.is_initialized = False
        self.has_calibrated = False
        self.target_depth = 0.0
        self.depth_tolerance = 0.125  # ±0.125m from target
        
        # Create and initialize sensor if available
        if MS5837_AVAILABLE:
            try:
                logger.info(f"Initializing MS5837 depth sensor on bus {bus_number}...")
                self.sensor = MS5837_02BA(bus=bus_number)  # Use 02BA model as it's common in ROVs
                
                if self.sensor.init():
                    # Configure for saltwater by default
                    self.sensor.setFluidDensity(DENSITY_SALTWATER)
                    self.available = True
                    self.is_initialized = True
                    logger.info("MS5837 depth sensor initialized successfully")
                    
                    # Take an initial reading and calibrate
                    self._read_sensor()
                    self.calibrate_at_surface()
                else:
                    logger.error("Failed to initialize MS5837 depth sensor")
            except Exception as e:
                logger.error(f"Error initializing depth sensor: {e}")
        else:
            logger.warning("MS5837 depth sensor not available. Using simulation mode.")
    
    def calibrate_at_surface(self) -> None:
        """Set the current depth as the zero reference point (surface)."""
        if not self.available:
            logger.warning("Cannot calibrate unavailable depth sensor")
            return
            
        try:
            self._read_sensor()
            self.initial_depth = self.last_depth
            self.has_calibrated = True
            logger.info(f"Depth sensor calibrated at surface. Initial reading: {self.initial_depth:.3f} m")
        except Exception as e:
            logger.error(f"Error calibrating depth sensor: {e}")
    
    def set_target_depth(self, target: float) -> None:
        """Set the target depth for PID control.
        
        Args:
            target: Target depth in meters
        """
        self.target_depth = target
        logger.info(f"Target depth set to {target:.3f} m")
    
    def set_depth_tolerance(self, tolerance: float) -> None:
        """Set the tolerance range around target depth.
        
        Args:
            tolerance: Tolerance in meters
        """
        self.depth_tolerance = tolerance
        logger.info(f"Depth tolerance set to ±{tolerance:.3f} m")

    def get_depth(self) -> float:
        """Get the current depth reading, relative to the calibrated surface.
        
        Returns:
            float: Current depth in meters (positive values = underwater)
        """
        self._read_sensor()
        return self.relative_depth

    def get_pressure(self) -> float:
        """Get the current pressure reading in millibars.
        
        Returns:
            float: Current pressure in mbar
        """
        self._read_sensor()
        return self.last_pressure
        
    def get_temperature(self) -> float:
        """Get the current temperature reading in Celsius.
        
        Returns:
            float: Current temperature in °C
        """
        self._read_sensor()
        return self.last_temperature
    
    def get_velocity(self) -> float:
        """Get the current vertical velocity.
        
        Returns:
            float: Vertical velocity in m/s (positive = descending, negative = ascending)
        """
        self._read_sensor()
        return self.current_velocity
    
    def get_depth_error(self) -> float:
        """Get the error from target depth.
        
        Returns:
            float: Error in meters (positive = need to descend, negative = need to ascend)
        """
        self._read_sensor()
        return self.target_depth - self.relative_depth
    
    def is_at_target_depth(self) -> bool:
        """Check if the current depth is within tolerance of the target.
        
        Returns:
            bool: True if within tolerance of target depth
        """
        error = abs(self.get_depth_error())
        return error <= self.depth_tolerance
    
    def get_all_data(self) -> Dict[str, float]:
        """Get all sensor readings in a dictionary.
        
        Returns:
            Dict with depth, pressure, temperature, velocity, and error values
        """
        self._read_sensor()
        return {
            "depth": self.relative_depth,
            "absolute_depth": self.last_depth,
            "pressure": self.last_pressure,
            "temperature": self.last_temperature,
            "velocity": self.current_velocity,
            "target_depth": self.target_depth,
            "depth_error": self.target_depth - self.relative_depth,
            "at_target": self.is_at_target_depth()
        }
    
    def _read_sensor(self) -> None:
        """Read values from the sensor if available and update stored values."""
        # Rate limiting
        now = time.time()
        if now - self.last_read_time < self.read_interval:
            return
            
        self.last_read_time = now
        
        if not self.available or not self.is_initialized:
            # In simulation mode or failed init, just return
            return
        
        try:
            # Read sensor data with highest oversampling for best precision
            if self.sensor.read(OSR_8192):
                # Store previous depth for velocity calculation
                self.previous_depth = self.last_depth
                
                # Update current readings
                self.last_depth = self.sensor.depth()
                self.last_pressure = self.sensor.pressure()
                self.last_temperature = self.sensor.temperature()
                
                # Calculate relative depth (based on calibration)
                if self.has_calibrated:
                    self.relative_depth = self.last_depth - self.initial_depth
                else:
                    self.relative_depth = self.last_depth
                
                # Calculate velocity (m/s)
                dt = now - self.previous_time
                if dt > 0:
                    self.current_velocity = (self.last_depth - self.previous_depth) / dt
                
                self.previous_time = now
                
        except Exception as e:
            logger.error(f"Error reading depth sensor: {e}")
    
    def close(self) -> None:
        """Close the sensor connection when done."""
        logger.info("Closing depth sensor connection")


def main():
    """Test function to demonstrate the depth sensor."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    # Create sensor
    depth_sensor = DepthSensor()
    if not depth_sensor.available:
        print("Depth sensor not available!")
        return
    
    # Set target depth for testing
    depth_sensor.set_target_depth(2.0)
    
    print("\nTaking continuous readings (Ctrl+C to exit)")
    try:
        while True:
            data = depth_sensor.get_all_data()
            
            print(f"Depth: {data['depth']:.3f} m")
            print(f"Pressure: {data['pressure']:.2f} mbar")
            print(f"Temperature: {data['temperature']:.2f} °C")
            print(f"Velocity: {data['velocity']:.3f} m/s")
            print(f"Target depth: {data['target_depth']:.3f} m")
            print(f"Depth error: {data['depth_error']:.3f} m")
            print(f"At target: {'Yes' if data['at_target'] else 'No'}")
            print("----------------------------------")
            
            time.sleep(0.5)
    
    except KeyboardInterrupt:
        print("\nExiting")
    finally:
        depth_sensor.close()


if __name__ == "__main__":
    main()