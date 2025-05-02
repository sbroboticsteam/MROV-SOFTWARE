#!/usr/bin/env python3

import time
import sys
from rov.hardware.pca9685 import PCA9685

# Initialize PCA9685
pca = PCA9685(bus_number=7)
pca.frequency = 50  # 50Hz for ESCs

# Simple function to set a pulse value to a channel
def set_pulse(channel, pulse_value):
    pca.channels[channel].duty_cycle = pulse_value
    print(f"Setting channel {channel} to pulse {pulse_value}")

def stop_motor(channel):
    neutral_pulse = 1500  # Neutral position (typically 1500μs)
    pulse_value = int((neutral_pulse / 20000) * 0xFFFF)  # Convert to 16-bit value
    pca.channels[channel].duty_cycle = pulse_value
    print(f"Stopping channel {channel}")

# Main program
if __name__ == "__main__":
    try:
        # Get channel from command line or use default
        channel = int(sys.argv[1]) if len(sys.argv) > 1 else 0
        
        # Get pulse value from command line or use default
        # Default is slightly above neutral (1550μs) to move slowly forward
        pulse_ms = float(sys.argv[2]) if len(sys.argv) > 2 else 1550
        
        # Convert pulse in milliseconds to 16-bit duty cycle value
        pulse_value = int((pulse_ms / 20000) * 0xFFFF)
        
        print(f"Testing motor on channel {channel} with pulse {pulse_ms}μs")
        print("Press Ctrl+C to stop")
        
        # Set the pulse
        set_pulse(channel, pulse_value)
        
        # Keep the program running until interrupted
        while True:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        # Stop the motor when Ctrl+C is pressed
        stop_motor(channel)
        pca.deinit()
        print("\nMotor stopped and PCA9685 deinitialized")
    except Exception as e:
        print(f"Error: {e}")
        try:
            stop_motor(channel)
            pca.deinit()
        except:
            pass
"""
        # Horizontal: 0(FL), 7(FR), 2(BL), 5(BR)
        # Vertical:   1(FL_UP), 4(FR_UP), 6(BR_UP), 3(BL_UP)
        self.thruster_channels = [0, 7, 2, 5, 1, 4, 6, 3]
        "python motorCalibration.py 3 1600"
        
        
        # Horizontal: 0(FL), 7(FR), 2(BL), 5(BR)
        # Vertical:   1(FL_UP), 4(FR_UP), 6(BR_UP), 3(BL_UP)
        self.thruster_channels = [0, 7, 2, 5, 1, 4, 6, 3]
        [13, 9, 10, 8, 11, 14, 15, 12]
"""
