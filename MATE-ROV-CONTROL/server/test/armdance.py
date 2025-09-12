import time
import math
from smbus2 import SMBus

# PCA9685 constants
PCA9685_ADDRESS = 0x40
MODE1 = 0x00
PRESCALE = 0xFE
LED0_ON_L = 0x06

class PCA9685:
    def __init__(self, bus_number=7, address=PCA9685_ADDRESS):
        self.bus = SMBus(bus_number)
        self.address = address
        self.channels = [PCA9685Channel(self, i) for i in range(16)]
        self.reset()

    def reset(self):
        self.bus.write_byte_data(self.address, MODE1, 0x00)
        time.sleep(0.01)

    @property
    def frequency(self):
        return self._frequency

    @frequency.setter
    def frequency(self, freq_hz):
        self._frequency = freq_hz
        prescale_val = int(25000000.0 / (4096 * freq_hz)) - 1

        mode1 = self.bus.read_byte_data(self.address, MODE1)
        self.bus.write_byte_data(self.address, MODE1, (mode1 & 0x7F) | 0x10)
        time.sleep(0.001)
        self.bus.write_byte_data(self.address, PRESCALE, prescale_val)
        time.sleep(0.001)
        self.bus.write_byte_data(self.address, MODE1, mode1)
        time.sleep(0.005)
        self.bus.write_byte_data(self.address, MODE1, mode1 | 0x80)
        time.sleep(0.001)

    def deinit(self):
        try:
            self.bus.close()
        except:
            pass

class PCA9685Channel:
    def __init__(self, pca, channel):
        self.pca = pca
        self.channel = channel
        self._duty_cycle = 0

    @property
    def duty_cycle(self):
        return self._duty_cycle

    @duty_cycle.setter
    def duty_cycle(self, value):
        self._duty_cycle = value
        on_value = 0
        off_value = value & 0xFFFF
        base_reg = LED0_ON_L + (4 * self.channel)

        self.pca.bus.write_byte_data(self.pca.address, base_reg, on_value & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 1, (on_value >> 8) & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 2, off_value & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 3, (off_value >> 8) & 0xFF)
        time.sleep(0.001)

class ArmDancer:
    """A class to make the ROV arm dance!"""
    
    def __init__(self, pca):
        self.pca = pca
        
        # Servo channel assignments based on your servo.py
        self.channels = {
            "wrist": 5,    # min: 900, max: 1800
            "elbow": 2,    # min: 900, max: 1950 (reduced from 2100)  
            "shoulder": 4, # min: 900, max: 2100
            "claw": 3      # min: 1630, max: 2050
        }
        
        # Servo limits - reduced elbow max by 150
        self.limits = {
            "wrist": {"min": 900, "max": 1800, "center": 1350},
            "elbow": {"min": 900, "max": 1950, "center": 1425},  # Reduced max from 2100 to 1950
            "shoulder": {"min": 900, "max": 2100, "center": 1500},
            "claw": {"min": 1630, "max": 2050, "center": 1840}
        }
        
        # Initialize all servos to center position
        self.current_positions = {}
        for servo in self.channels.keys():
            self.current_positions[servo] = self.limits[servo]["center"]
            self._set_servo_pulse(servo, self.limits[servo]["center"])
        
        time.sleep(1)  # Let servos reach initial position

    def _set_servo_pulse(self, servo_name, pulse_width):
        """Set servo to specific pulse width"""
        channel = self.channels[servo_name]
        
        # Clamp to limits
        min_pulse = self.limits[servo_name]["min"]
        max_pulse = self.limits[servo_name]["max"]
        pulse_width = max(min_pulse, min(max_pulse, pulse_width))
        
        # Convert to duty cycle
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[channel].duty_cycle = duty_cycle
        
        self.current_positions[servo_name] = pulse_width
        time.sleep(0.001)

    def smooth_move(self, servo_name, target_pulse, duration=0.5):
        """Smoothly move servo to target position over given duration"""
        start_pulse = self.current_positions[servo_name]
        steps = int(duration * 50)  # 50 steps per second
        
        for i in range(steps + 1):
            progress = i / steps
            current_pulse = start_pulse + (target_pulse - start_pulse) * progress
            self._set_servo_pulse(servo_name, int(current_pulse))
            time.sleep(duration / steps)

    def shake_hands(self):
        """Make the arm perform a handshake - reach out, grab, and shake"""
        print("🤝 Let's shake hands!")
        
        # Step 1: Extend arm to handshake position
        print("   Reaching out for handshake...")
        self.smooth_move("shoulder", 1425, 0.8)  # Extend out
        self.smooth_move("elbow", 1460, 0.6)     # Straighten elbow
        self.smooth_move("wrist", 1350, 0.4)     # Center wrist
        
        # Step 2: Open claw in preparation
        print("   Opening hand...")
        self.smooth_move("claw", 2000, 0.5)      # Open claw wide
        time.sleep(0.3)
        
        # Step 3: Close claw as if grabbing a hand
        print("   Grabbing hand...")
        self.smooth_move("claw", 1750, 0.4)      # Close to grab (not too tight)
        time.sleep(0.2)
        
        # Step 4: Perform the handshake motion (up and down)
        print("   Shaking hands!")
        for shake in range(5):
            # Up motion
            self.smooth_move("elbow", 1380, 0.25)   # Slight up
            self.smooth_move("wrist", 1280, 0.25)   # Slight wrist adjustment
            time.sleep(0.05)
            
            # Down motion  
            self.smooth_move("elbow", 1500, 0.25)   # Back down
            self.smooth_move("wrist", 1420, 0.25)   # Wrist back
            time.sleep(0.05)
        
        # Step 5: Release the handshake
        print("   Releasing hand...")
        self.smooth_move("claw", 2000, 0.4)      # Open claw
        time.sleep(0.3)
        
        # Step 6: Polite withdrawal
        print("   Nice to meet you!")
        self.smooth_move("wrist", 1350, 0.3)     # Center wrist
        time.sleep(0.2)

    def wave_hello(self):
        """Make the arm wave hello"""
        print("🤖 Waving hello!")
        
        # Extend arm
        self.smooth_move("shoulder", 1425, 0.8)  # Extend out
        self.smooth_move("elbow", 1460, 0.6)     # Straighten elbow
        time.sleep(0.2)
        
        # Wave motion with wrist
        for _ in range(4):
            self.smooth_move("wrist", 1200, 0.3)  # Left
            self.smooth_move("wrist", 1600, 0.3)  # Right
        
        # Return to center
        self.smooth_move("wrist", 1350, 0.3)

    def robot_dance(self):
        """Classic robot dance moves"""
        print("🤖 Doing the robot dance!")
        
        # Robot jerky movements - updated with new elbow limits
        positions = [
            {"shoulder": 1800, "elbow": 1200, "wrist": 900},   # Up and bent
            {"shoulder": 1200, "elbow": 1800, "wrist": 1600},  # Down and extended
            {"shoulder": 1600, "elbow": 1400, "wrist": 1100},  # Mid position
            {"shoulder": 1400, "elbow": 1600, "wrist": 1500}   # Another mid
        ]
        
        for pos in positions:
            for servo, pulse in pos.items():
                self._set_servo_pulse(servo, pulse)
            time.sleep(0.8)  # Hold position
            
            # Claw snap
            self._set_servo_pulse("claw", 1700)  # Close
            time.sleep(0.1)
            self._set_servo_pulse("claw", 1950)  # Open
            time.sleep(0.2)

    def smooth_sine_wave(self):
        """Smooth sine wave motion across all joints"""
        print("🌊 Performing sine wave dance!")
        
        duration = 8  # 8 seconds
        steps = 200
        
        for i in range(steps):
            t = (i / steps) * duration
            
            # Different frequency sine waves for each joint - adjusted for new elbow limits
            shoulder_offset = math.sin(t * 2) * 300  # 2 Hz
            elbow_offset = math.sin(t * 1.5) * 250   # 1.5 Hz, reduced range
            wrist_offset = math.sin(t * 3) * 200     # 3 Hz
            claw_offset = math.sin(t * 4) * 100      # 4 Hz
            
            # Apply offsets to center positions
            self._set_servo_pulse("shoulder", int(1500 + shoulder_offset))
            self._set_servo_pulse("elbow", int(1425 + elbow_offset))  # Using new center
            self._set_servo_pulse("wrist", int(1350 + wrist_offset))
            self._set_servo_pulse("claw", int(1840 + claw_offset))
            
            time.sleep(duration / steps)

    def figure_eight(self):
        """Make the end effector trace a figure-8 in space"""
        print("∞ Drawing figure-8 in the air!")
        
        steps = 100
        for i in range(steps):
            t = (i / steps) * 4 * math.pi  # Two full cycles
            
            # Figure-8 parametric equations
            x = math.sin(t)
            y = math.sin(t) * math.cos(t)
            
            # Map to servo positions (scaled appropriately) - adjusted for new elbow limits
            shoulder_pulse = int(1500 + x * 300)
            elbow_pulse = int(1425 + y * 250)  # Reduced range and using new center
            wrist_pulse = int(1350 + x * 150)
            
            self._set_servo_pulse("shoulder", shoulder_pulse)
            self._set_servo_pulse("elbow", elbow_pulse) 
            self._set_servo_pulse("wrist", wrist_pulse)
            
            time.sleep(0.08)

    def grabby_dance(self):
        """Claw opening and closing in rhythm"""
        print("✋ Grabby dance time!")
        
        beats = [0.3, 0.3, 0.6, 0.3, 0.3, 0.6, 0.2, 0.2, 0.2, 0.8]
        
        for beat in beats:
            # Quick grab motion
            self.smooth_move("claw", 1700, beat/3)  # Close quickly
            self.smooth_move("claw", 2000, beat*2/3)  # Open slower
            
            # Add some arm movement
            shoulder_pos = 1500 + (200 if beat > 0.5 else -200)
            self.smooth_move("shoulder", shoulder_pos, beat)

    def funky_chicken(self):
        """Funky chicken dance moves"""
        print("🐔 Doing the funky chicken!")
        
        for _ in range(6):
            # Wing flap motion - adjusted for new elbow limits
            self.smooth_move("elbow", 1800, 0.2)    # Down (reduced from 2000)
            self.smooth_move("shoulder", 1200, 0.2)  # In
            time.sleep(0.1)
            
            self.smooth_move("elbow", 1200, 0.2)    # Up  
            self.smooth_move("shoulder", 1800, 0.2)  # Out
            time.sleep(0.1)
            
            # Peck motion with wrist
            self.smooth_move("wrist", 1000, 0.15)
            self.smooth_move("wrist", 1600, 0.15)

    def return_to_neutral(self):
        """Return all servos to neutral position"""
        print("🏠 Returning to neutral position...")
        
        for servo in self.channels.keys():
            center = self.limits[servo]["center"]
            self.smooth_move(servo, center, 1.0)
        
        time.sleep(0.5)

    def dance_sequence(self):
        """Perform the full dance sequence"""
        print("🎭 Starting ROV ARM DANCE SEQUENCE! 🎭")
        print("=" * 50)
        
        try:
            self.wave_hello()
            time.sleep(1)
            
            self.shake_hands()
            time.sleep(1)
            
            self.robot_dance()
            time.sleep(1)
            
            self.smooth_sine_wave()
            time.sleep(1)
            
            self.figure_eight()
            time.sleep(1)
            
            self.grabby_dance()
            time.sleep(1)
            
            self.funky_chicken()
            time.sleep(1)
            
            self.wave_hello()  # Say goodbye
            
        except KeyboardInterrupt:
            print("\n⏹️ Dance interrupted!")
        finally:
            self.return_to_neutral()
            print("🎉 Dance sequence complete!")

def main():
    print("🤖 ROV ARM DANCER 🤖")
    print("Initializing PCA9685...")
    
    # Initialize PCA9685
    pca = PCA9685(bus_number=7)
    pca.frequency = 50
    
    # Create dancer
    dancer = ArmDancer(pca)
    
    print("\nChoose a dance:")
    print("1. Full dance sequence")
    print("2. Wave hello")
    print("3. Shake hands")
    print("4. Robot dance")
    print("5. Sine wave")
    print("6. Figure-8")
    print("7. Grabby dance")
    print("8. Funky chicken")
    print("9. Return to neutral")
    print("q. Quit")
    
    try:
        while True:
            choice = input("\nEnter choice (1-9 or q): ").strip().lower()
            
            if choice == 'q':
                break
            elif choice == '1':
                dancer.dance_sequence()
            elif choice == '2':
                dancer.wave_hello()
                dancer.return_to_neutral()
            elif choice == '3':
                dancer.shake_hands()
                dancer.return_to_neutral()
            elif choice == '4':
                dancer.robot_dance()
                dancer.return_to_neutral()
            elif choice == '5':
                dancer.smooth_sine_wave()
                dancer.return_to_neutral()
            elif choice == '6':
                dancer.figure_eight()
                dancer.return_to_neutral()
            elif choice == '7':
                dancer.grabby_dance()
                dancer.return_to_neutral()
            elif choice == '8':
                dancer.funky_chicken()
                dancer.return_to_neutral()
            elif choice == '9':
                dancer.return_to_neutral()
            else:
                print("Invalid choice!")
                
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        dancer.return_to_neutral()
        pca.deinit()
        print("PCA9685 closed. Goodbye! 👋")

if __name__ == '__main__':
    main()