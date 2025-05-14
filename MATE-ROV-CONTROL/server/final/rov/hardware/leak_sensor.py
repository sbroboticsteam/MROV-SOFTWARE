try:
    import Jetson.GPIO as GPIO
except ImportError:
    try:
        import RPi.GPIO as GPIO  # Fallback for testing on other platforms
    except ImportError:
        import sys
        print("ERROR: Neither Jetson.GPIO nor RPi.GPIO is available.")
        print("Please install the appropriate package for your hardware:")
        print("  Jetson: sudo apt-get install -y python3-pip && sudo pip3 install Jetson.GPIO")
        print("  Raspberry Pi: sudo apt-get install -y python3-pip && sudo pip3 install RPi.GPIO")
        sys.exit(1)
        
import time
import threading
import logging
import sys

logger = logging.getLogger("ROV")

class LeakSensor:
    """Blue Robotics SOS Leak Sensor interface"""
    
    def __init__(self, pin=12, callback=None):
        """Initialize the leak sensor on the specified GPIO pin."""
        self.pin = pin
        self.callback = callback
        self.leak_detected = False
        self.available = False
        self.running = False
        self.thread = None
        
        try:
            # Configure GPIO
            GPIO.setmode(GPIO.BCM)  # Use BCM numbering
            
            # IMPORTANT: Set pin mode and disable internal pull resistors
            # Configure as input without internal pull resistor
            GPIO.setup(self.pin, GPIO.IN)
            
            # Log initial state - helpful for debugging
            initial_state = GPIO.input(self.pin)
            logger.info(f"Leak sensor initialized on GPIO {self.pin}. Initial state: {initial_state}")
            
            # Add event detection for BOTH rising and falling edges to ensure detection
            GPIO.add_event_detect(self.pin, GPIO.BOTH, callback=self._pin_change_callback, bouncetime=300)
            
            self.available = True
        except Exception as e:
            logger.error(f"Failed to initialize leak sensor: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # Replace the existing callback method with this one
    def _pin_change_callback(self, channel):
        """Called when pin state changes"""
        current_state = GPIO.input(self.pin)
        
        logger.info(f"Pin {self.pin} state changed to: {current_state}")
        
        if current_state == GPIO.HIGH:  # HIGH = leak detected
            if not self.leak_detected:
                self.leak_detected = True
                logger.critical("LEAK DETECTED! Take immediate action!")
                if self.callback:
                    self.callback()
        elif current_state == GPIO.LOW:  # LOW = no leak
            if self.leak_detected:
                self.leak_detected = False
                logger.info("Leak condition cleared")
    
    def start_monitoring(self):
        """Start a monitoring thread to periodically check the sensor status"""
        if not self.available:
            logger.warning("Leak sensor not available, monitoring not started")
            return False
            
        self.running = True
        self.thread = threading.Thread(target=self._monitor_sensor)
        self.thread.daemon = True
        self.thread.start()
        logger.info("Leak sensor monitoring thread started")
        return True
    
    def _monitor_sensor(self):
        """Background thread to periodically check sensor status"""
        logger.info("Leak sensor monitoring thread running")
        
        while self.running:
            # Check current state (adds redundancy to the interrupt)
            current_state = GPIO.input(self.pin)
            if current_state == GPIO.HIGH and not self.leak_detected:
                self.leak_detected = True
                logger.critical("LEAK DETECTED from polling! Take immediate action!")
                if self.callback:
                    self.callback()
            
            # Reset state if leak is no longer detected (for testing purposes)
            if current_state == GPIO.LOW and self.leak_detected:
                logger.info("Leak condition cleared")
                self.leak_detected = False
                
            time.sleep(0.5)  # Check every 500ms
            
        logger.info("Leak sensor monitoring thread stopped")
    
    def get_status(self):
        """Get the current leak sensor status
        
        Returns:
            dict: Dictionary with sensor status
        """
        if not self.available:
            return {"available": False, "leak_detected": False}
            
        return {
            "available": True,
            "leak_detected": self.leak_detected,
            "pin": self.pin
        }
    
    def close(self):
        """Clean up resources"""
        self.running = False
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
            
        if self.available:
            try:
                GPIO.remove_event_detect(self.pin)
                # Don't cleanup all GPIO as other components might be using it
                # Just reset this particular pin
                GPIO.setup(self.pin, GPIO.IN)
            except:
                pass
            
        logger.info("Leak sensor resources released")

if __name__ == "__main__":
    import sys
    
    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.DEBUG,  # Set to DEBUG for more information
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    def test_callback():
        print("\n*** LEAK CALLBACK EXECUTED! ***\n")
    
    try:
        # Default to GPIO pin 12, but allow command-line override
        pin = 22
        if len(sys.argv) > 1:
            pin = int(sys.argv[1])
            
        print(f"Testing leak sensor on GPIO pin {pin}")
        print("Press Ctrl+C to exit.")
        print("Simulate leak by connecting the sensor pin to 3.3V/5V (HIGH)")
        
        # Dump GPIO information
        print("\nGPIO Information:")
        print(f"GPIO Version: {GPIO.VERSION}")
        print(f"GPIO Mode: {GPIO.getmode()}")
        
        # Create and start sensor
        sensor = LeakSensor(pin=pin, callback=test_callback)
        
        if sensor.available:
            sensor.start_monitoring()
            
            # Main loop to show current status
            while True:
                status = sensor.get_status()
                current_state = GPIO.input(pin)
                print(f"Sensor status: {'LEAK DETECTED!' if status['leak_detected'] else 'No leak'}, Raw pin state: {current_state}")
                time.sleep(1)
        else:
            print("ERROR: Sensor not available. Check connections and permissions.")
    
    except KeyboardInterrupt:
        print("\nTest terminated by user.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        print(traceback.format_exc())
    finally:
        # Clean up
        if 'sensor' in locals() and sensor.available:
            sensor.close()
        try:
            GPIO.cleanup()
        except:
            pass