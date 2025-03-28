import json
from adafruit_pca9685 import PCA9685
from board import SCL, SDA
import busio
from time import sleep
import sys

class ESC:
    def __init__(self, channel, pca):
        """
        Initializes an individual ESC.
        :param channel: PCA9685 channel used for the ESC's PWM signal.
        :param pca: The PCA9685 instance.
        """
        self.channel = channel
        self.pca = pca
        # PWM constants for ESC (in microseconds)
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1100  # Full reverse
        self.MAX_PULSE = 1900  # Full forward
        self.FORWARD_MIN = 1525
        self.REVERSE_MAX = 1475
        
    def initialize(self):
        """
        Initialize the ESC with a 1500μs pulse.
        """
        self._set_pulse_width(self.STOP_PULSE)
        sleep(2)  # Allow time for ESC to recognize the initialization signal
        print(f"ESC on channel {self.channel} initialized")
    
    def set_state(self, state):
        """
        Sets the ESC state based on the given value.
        :param state: A float between -1.0 and 1.0. Positive values indicate forward motion,
                      negative values indicate reverse, and zero stops the ESC.
        """
        if state > 0:
            # Forward: map 0->1 to FORWARD_MIN->MAX_PULSE
            pulse_width = self.FORWARD_MIN + (state * (self.MAX_PULSE - self.FORWARD_MIN))
        elif state < 0:
            # Reverse: map -1->0 to MIN_PULSE->REVERSE_MAX
            pulse_width = self.MIN_PULSE + (abs(state) * (self.REVERSE_MAX - self.MIN_PULSE))
        else:
            # Stop
            pulse_width = self.STOP_PULSE
            
        self._set_pulse_width(pulse_width)

    def _set_pulse_width(self, pulse_width):
        """
        Sets the PWM pulse width in microseconds.
        :param pulse_width: Desired pulse width in microseconds (1100-1900).
        """
        # PCA9685 works with duty cycle values from 0 to 0xFFFF
        # Convert microseconds to duty cycle
        # For 50Hz PWM frequency, a period is 20,000 microseconds
        # So the duty cycle is (pulse_width / 20,000)
        duty_cycle = int((pulse_width / 20000.0) * 0xFFFF)
        self.pca.channels[self.channel].duty_cycle = duty_cycle

class ESCController:
    def __init__(self, esc_channels, pca):
        """
        Initializes a collection of ESC objects.
        :param esc_channels: A list of channel numbers for the ESCs.
        :param pca: The PCA9685 instance to be used by all ESCs.
        """
        self.escs = []
        for channel in esc_channels:
            esc = ESC(channel, pca)
            self.escs.append(esc)
        
    def initialize_all(self):
        """
        Initializes all ESCs.
        """
        print("Initializing all ESCs...")
        for esc in self.escs:
            esc.initialize()
        print("All ESCs initialized.")

    def set_all_states(self, states):
        """
        Updates all ESCs based on the list of state values.
        :param states: A list of numbers (each between -1.0 and 1.0).
        """
        if len(states) != len(self.escs):
            print(f"Expected {len(self.escs)} states, got {len(states)}")
            return
        for esc, state in zip(self.escs, states):
            esc.set_state(state)

    def stop_all(self):
        """Stops all ESCs by sending the stop signal (1500μs)."""
        for esc in self.escs:
            esc.set_state(0)

def run_direct_test(esc_controller):
    """
    Runs a direct test sequence on all ESCs.
    """
    print("\n===== ESC DIRECT TEST MODE =====")
    print("Testing each ESC in sequence...")
    
    # Test each ESC individually
    for i, esc in enumerate(esc_controller.escs):
        print(f"\nTesting ESC #{i+1} on channel {esc.channel}")
        print("Forward 25%...")
        esc.set_state(0.1)  # 25% forward
        sleep(2)
        
        print("Stop...")
        esc.set_state(0)
        sleep(1)
        
        print("Reverse 25%...")
        esc.set_state(-0.1)  # 25% reverse
        sleep(2)
        
        print("Stop...")
        esc.set_state(0)
        sleep(1)
    
    print("\nTesting all ESCs together...")
    print("All forward 50%...")
    esc_controller.set_all_states([0.15] * len(esc_controller.escs))
    sleep(3)
    
    print("All stop...")
    esc_controller.stop_all()
    sleep(1)
    
    print("All reverse 50%...")
    esc_controller.set_all_states([-0.15] * len(esc_controller.escs))
    sleep(3)
    
    print("All stop...")
    esc_controller.stop_all()
    
    print("\n===== Test sequence complete =====")

def run_interactive_mode(esc_controller):
    """
    Allows interactive control of ESCs through keyboard input.
    """
    print("\n===== ESC INTERACTIVE MODE =====")
    print("Enter commands to control ESCs:")
    print("  all X    - Set all ESCs to X (-1.0 to 1.0)")
    print("  N X      - Set ESC #N to X (-1.0 to 1.0)")
    print("  stop     - Stop all ESCs")
    print("  quit     - Exit the program")
    
    while True:
        try:
            cmd = input("\nCommand: ").strip().lower()
            
            if cmd == "quit":
                break
            elif cmd == "stop":
                esc_controller.stop_all()
                print("All ESCs stopped.")
            elif cmd.startswith("all "):
                try:
                    value = float(cmd.split()[1])
                    if -1.0 <= value <= 1.0:
                        esc_controller.set_all_states([value] * len(esc_controller.escs))
                        print(f"All ESCs set to {value}")
                    else:
                        print("Value must be between -1.0 and 1.0")
                except (IndexError, ValueError):
                    print("Invalid command format. Use 'all X' where X is between -1.0 and 1.0")
            elif " " in cmd:
                try:
                    parts = cmd.split()
                    esc_num = int(parts[0])
                    value = float(parts[1])
                    
                    if 1 <= esc_num <= len(esc_controller.escs) and -1.0 <= value <= 1.0:
                        esc_controller.escs[esc_num-1].set_state(value)
                        print(f"ESC #{esc_num} set to {value}")
                    else:
                        print(f"ESC number must be 1-{len(esc_controller.escs)} and value between -1.0 and 1.0")
                except (IndexError, ValueError):
                    print("Invalid command format. Use 'N X' where N is ESC number and X is between -1.0 and 1.0")
            else:
                print("Unknown command")
        
        except KeyboardInterrupt:
            print("\nExiting interactive mode.")
            break

def main():
    # ESC configuration - just need the channel numbers for each ESC
    # Using the same channel numbers as in the original configuration
    esc_channels = [8, 9, 10, 11, 12, 13, 14, 15]  # Channels for 8 ESCs

    # Set up I2C and initialize PCA9685
    print("Initializing PCA9685...")
    i2c = busio.I2C(SCL, SDA)
    pca = PCA9685(i2c)
    # Set PWM frequency to 50Hz (standard for most ESCs)
    pca.frequency = 50
    print(f"PCA9685 frequency set to {pca.frequency}Hz")

    # Initialize ESC controller with the channel configurations
    esc_controller = ESCController(esc_channels, pca)
    
    # Initialize all ESCs before use
    esc_controller.initialize_all()
    
    try:
        # Check for command line arguments
        if len(sys.argv) > 1 and sys.argv[1] == "test":
            run_direct_test(esc_controller)
        else:
            run_interactive_mode(esc_controller)
    finally:
        # Ensure proper cleanup
        print("Stopping all ESCs...")
        esc_controller.stop_all()
        pca.deinit()
        print("PCA9685 deinitialized and cleanup complete.")

if __name__ == '__main__':
    main()
