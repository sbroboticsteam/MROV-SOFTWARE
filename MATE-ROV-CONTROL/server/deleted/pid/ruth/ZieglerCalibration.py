import time
import json
import signal
import logging
import argparse
import threading
import numpy as np
from datetime import datetime

# Import ROV components
from rov.hardware.pca9685 import PCA9685
from classesForChatPID.thruster import Thruster
from classesForChatPID.imu_sensor import IMUSensor
from rov.ethernet_manager import EthernetManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("pid_calibration.log"), logging.StreamHandler()]
)
logger = logging.getLogger("PID_Calibration")

class PIDCalibrator:
    """Class for calibrating PID controllers using Ziegler-Nichols method."""
    
    def __init__(self, save_file="pid_auto_calibration.json"):
        logger.info("Initializing PID calibrator")
        
        # Save file path
        self.save_file = save_file
        
        # Initialize PCA9685 PWM controller and thrusters
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50  # 50Hz for ESCs
        
        # Thruster configuration (same as ROV)
        self.thruster_channels = [13, 9, 10, 8, 11, 14, 15, 12]
        self.thruster_names = [
            "FrontLeft", "FrontRight", "BackLeft", "BackRight",
            "FrontLeftUp", "FrontRightUp", "BackRightUp", "BackLeftUp"
        ]
        
        self.thrusters = []
        for i, channel in enumerate(self.thruster_channels):
            name = self.thruster_names[i] if i < len(self.thruster_names) else f"Thruster{i}"
            self.thrusters.append(Thruster(channel, self.pca, name=name))
        
        # Initialize IMU
        self.imu = IMUSensor()
        if not self.imu.available:
            logger.error("IMU not available - calibration cannot proceed")
            raise RuntimeError("IMU not available")
            
        # Initialize orientation tracking
        self.orientation_thread = None
        self.orientation_running = False
        self.orientation_lock = threading.Lock()
        self.current_heading = 0
        self.current_roll = 0
        self.current_pitch = 0
        
        # Data collection for oscillation analysis
        self.data_collection = {
            "heading": {"values": [], "times": [], "setpoint": 0},
            "roll": {"values": [], "times": [], "setpoint": 0},
            "pitch": {"values": [], "times": [], "setpoint": 0}
        }
        
        # Calibration results
        self.calibration_results = {
            "heading_pid": {"Kp": 0.0, "Ki": 0.0, "Kd": 0.0},
            "roll_pid": {"Kp": 0.0, "Ki": 0.0, "Kd": 0.0},
            "pitch_pid": {"Kp": 0.0, "Ki": 0.0, "Kd": 0.0}
        }
        
        # Control flags
        self.running = False
        self.current_calibration = None
        
        # Safety limits
        self.max_test_duration = 30  # seconds
        self.safety_limits = {
            "heading": 45,  # maximum heading deviation in degrees
            "roll": 30,     # maximum roll angle in degrees
            "pitch": 30     # maximum pitch angle in degrees
        }
        
        logger.info("PID calibrator initialized")
    
    def start_orientation_thread(self):
        """Start thread to continuously update orientation data from IMU."""
        self.orientation_running = True
        self.orientation_thread = threading.Thread(target=self._orientation_updater)
        self.orientation_thread.daemon = True
        self.orientation_thread.start()
        logger.info("Orientation update thread started")
        
    def _orientation_updater(self):
        """Thread function to update orientation data from IMU."""
        logger.info("Orientation updater thread running")
        while self.orientation_running:
            try:
                heading, roll, pitch = self.imu.get_orientation()
                
                with self.orientation_lock:
                    self.current_heading = heading
                    self.current_roll = roll
                    self.current_pitch = pitch
                    
                    # If currently collecting data for calibration, store measurements
                    if self.current_calibration:
                        self._record_measurement()
                        
                # Small sleep to prevent overwhelming the CPU
                time.sleep(0.01)
            except Exception as e:
                logger.error(f"Error in orientation updater: {e}")
                time.sleep(0.1)  # Wait a bit longer on error
                
        logger.info("Orientation updater thread stopped")
    
    def _record_measurement(self):
        """Record current measurements for the active calibration."""
        if not self.current_calibration:
            return
            
        current_time = time.time()
        
        if self.current_calibration == "heading":
            self.data_collection["heading"]["values"].append(self.current_heading)
            self.data_collection["heading"]["times"].append(current_time)
        elif self.current_calibration == "roll":
            self.data_collection["roll"]["values"].append(self.current_roll)
            self.data_collection["roll"]["times"].append(current_time)
        elif self.current_calibration == "pitch":
            self.data_collection["pitch"]["values"].append(self.current_pitch)
            self.data_collection["pitch"]["times"].append(current_time)
    
    def initialize_thrusters(self):
        """Initialize all thruster ESCs."""
        logger.info("Initializing all thrusters...")
        for thruster in self.thrusters:
            thruster.initialize()
        logger.info("All thrusters initialized")
    
    def stop_thrusters(self):
        """Stop all thrusters."""
        logger.info("Stopping all thrusters...")
        for thruster in self.thrusters:
            thruster.stop()
        logger.info("All thrusters stopped")
    
    def calibrate_heading(self, kp_start=0.05, kp_step=0.05, test_duration=15):
        """Calibrate heading PID using Ziegler-Nichols method."""
        logger.info(f"Starting heading calibration with Kp={kp_start}, step={kp_step}")
        
        self.current_calibration = "heading"
        
        # Get current heading as setpoint
        with self.orientation_lock:
            setpoint = self.current_heading
            self.data_collection["heading"]["setpoint"] = setpoint
            logger.info(f"Heading calibration setpoint: {setpoint:.1f}°")
        
        # Perform Ziegler-Nichols step test
        ultimate_gain, oscillation_period = self._perform_ziegler_nichols(
            "heading", setpoint, kp_start, kp_step, test_duration
        )
        
        if ultimate_gain and oscillation_period:
            # Calculate PID parameters using Ziegler-Nichols formula
            kp = 0.6 * ultimate_gain
            ki = 1.2 * ultimate_gain / oscillation_period
            kd = 0.075 * ultimate_gain * oscillation_period
            
            self.calibration_results["heading_pid"]["Kp"] = kp
            self.calibration_results["heading_pid"]["Ki"] = ki
            self.calibration_results["heading_pid"]["Kd"] = kd
            
            logger.info(f"Heading PID calibration complete: Kp={kp:.4f}, Ki={ki:.4f}, Kd={kd:.4f}")
        else:
            logger.warning("Heading calibration did not yield valid results")
        
        self.current_calibration = None
        return ultimate_gain is not None
    
    def calibrate_roll(self, kp_start=0.05, kp_step=0.05, test_duration=15):
        """Calibrate roll PID using Ziegler-Nichols method."""
        logger.info(f"Starting roll calibration with Kp={kp_start}, step={kp_step}")
        
        self.current_calibration = "roll"
        
        # Use 0 as setpoint (level position)
        setpoint = 0
        self.data_collection["roll"]["setpoint"] = setpoint
        logger.info(f"Roll calibration setpoint: {setpoint:.1f}°")
        
        # Perform Ziegler-Nichols step test
        ultimate_gain, oscillation_period = self._perform_ziegler_nichols(
            "roll", setpoint, kp_start, kp_step, test_duration
        )
        
        if ultimate_gain and oscillation_period:
            # Calculate PID parameters using Ziegler-Nichols formula
            kp = 0.6 * ultimate_gain
            ki = 1.2 * ultimate_gain / oscillation_period
            kd = 0.075 * ultimate_gain * oscillation_period
            
            self.calibration_results["roll_pid"]["Kp"] = kp
            self.calibration_results["roll_pid"]["Ki"] = ki
            self.calibration_results["roll_pid"]["Kd"] = kd
            
            logger.info(f"Roll PID calibration complete: Kp={kp:.4f}, Ki={ki:.4f}, Kd={kd:.4f}")
        else:
            logger.warning("Roll calibration did not yield valid results")
        
        self.current_calibration = None
        return ultimate_gain is not None
    
    def calibrate_pitch(self, kp_start=0.05, kp_step=0.05, test_duration=15):
        """Calibrate pitch PID using Ziegler-Nichols method."""
        logger.info(f"Starting pitch calibration with Kp={kp_start}, step={kp_step}")
        
        self.current_calibration = "pitch"
        
        # Use 0 as setpoint (level position)
        setpoint = 0
        self.data_collection["pitch"]["setpoint"] = setpoint
        logger.info(f"Pitch calibration setpoint: {setpoint:.1f}°")
        
        # Perform Ziegler-Nichols step test
        ultimate_gain, oscillation_period = self._perform_ziegler_nichols(
            "pitch", setpoint, kp_start, kp_step, test_duration
        )
        
        if ultimate_gain and oscillation_period:
            # Calculate PID parameters using Ziegler-Nichols formula
            kp = 0.6 * ultimate_gain
            ki = 1.2 * ultimate_gain / oscillation_period
            kd = 0.075 * ultimate_gain * oscillation_period
            
            self.calibration_results["pitch_pid"]["Kp"] = kp
            self.calibration_results["pitch_pid"]["Ki"] = ki
            self.calibration_results["pitch_pid"]["Kd"] = kd
            
            logger.info(f"Pitch PID calibration complete: Kp={kp:.4f}, Ki={ki:.4f}, Kd={kd:.4f}")
        else:
            logger.warning("Pitch calibration did not yield valid results")
        
        self.current_calibration = None
        return ultimate_gain is not None
    
    def _perform_ziegler_nichols(self, axis, setpoint, kp_start, kp_step, max_duration, max_tests=15):
        """
        Perform Ziegler-Nichols ultimate gain test for the specified axis.
        
        The method increases Kp until the system shows consistent oscillations,
        then measures the ultimate gain (Ku) and oscillation period (Tu).
        """
        logger.info(f"Starting Ziegler-Nichols test for {axis}")
        
        # Clear previous data
        self.data_collection[axis]["values"] = []
        self.data_collection[axis]["times"] = []
        
        # Safety check function to abort test if limits exceeded
        def check_safety_limits():
            if axis == "heading":
                heading_error = abs((self.current_heading - setpoint + 180) % 360 - 180)
                return heading_error > self.safety_limits["heading"]
            elif axis == "roll":
                return abs(self.current_roll) > self.safety_limits["roll"]
            elif axis == "pitch":
                return abs(self.current_pitch) > self.safety_limits["pitch"]
            return False
        
        # Initialize test parameters
        current_kp = kp_start
        ultimate_gain = None
        oscillation_period = None
        max_tests = 15  # Maximum number of Kp values to test
        test_count = 0
        
        # Variables to detect and measure oscillations
        prev_error = 0
        zero_crossings = []
        
        try:
            # Test progressively higher Kp values
            while test_count < max_tests and not ultimate_gain:
                logger.info(f"Testing Kp={current_kp:.4f} for {axis}")
                
                # Reset test data for this Kp value
                self.data_collection[axis]["values"] = []
                self.data_collection[axis]["times"] = []
                zero_crossings = []
                
                # Start time for this test
                start_time = time.time()
                last_time = start_time
                
                # Apply first correction
                self._apply_correction(axis, setpoint, current_kp)
                
                # Monitor system response for this Kp value
                while time.time() - start_time < max_duration:
                    # Apply P-only controller correction
                    self._apply_correction(axis, setpoint, current_kp)
                    
                    # Calculate current error
                    current_error = self._get_error(axis, setpoint)
                    
                    # Detect zero crossings (error sign change)
                    if prev_error * current_error < 0:
                        zero_crossings.append(time.time())
                        
                    prev_error = current_error
                    
                    # Safety check - stop if limits exceeded
                    if check_safety_limits():
                        logger.warning(f"Safety limit exceeded for {axis}. Stopping test.")
                        self.stop_thrusters()
                        time.sleep(2)  # Wait for system to stabilize
                        break
                    
                    # Check if we've detected enough oscillations to measure period
                    if len(zero_crossings) >= 6:  # Need at least 3 full oscillations
                        # Calculate average oscillation period
                        periods = []
                        for i in range(2, len(zero_crossings)):
                            period = (zero_crossings[i] - zero_crossings[i-2]) / 1.0  # One full cycle
                            periods.append(period)
                        
                        avg_period = sum(periods) / len(periods)
                        
                        # Check if oscillations are consistent (low variance)
                        period_stddev = np.std(periods) if len(periods) > 1 else 0
                        if period_stddev < 0.2 * avg_period:  # Standard deviation < 20% of mean
                            logger.info(f"Sustained oscillations detected with Kp={current_kp:.4f}, period={avg_period:.3f}s")
                            ultimate_gain = current_kp
                            oscillation_period = avg_period
                            break
                    
                    # Prevent CPU hogging
                    time.sleep(0.02)
                
                # If no sustained oscillations detected, increase Kp
                if not ultimate_gain:
                    # Stop thrusters between tests
                    self.stop_thrusters()
                    time.sleep(1.0)  # Wait for system to stabilize
                    
                    # Increase Kp for next test
                    current_kp += kp_step
                    test_count += 1
                    
            # After all tests, stop thrusters
            self.stop_thrusters()
            
            # Log result
            if ultimate_gain:
                logger.info(f"Ziegler-Nichols test complete for {axis}: Ku={ultimate_gain:.4f}, Tu={oscillation_period:.3f}s")
            else:
                logger.warning(f"Ziegler-Nichols test for {axis} did not produce sustained oscillations")
                
            return ultimate_gain, oscillation_period
            
        except Exception as e:
            logger.error(f"Error during Ziegler-Nichols test for {axis}: {e}")
            self.stop_thrusters()
            return None, None
    
    def _get_error(self, axis, setpoint):
        """Calculate error for the specified axis."""
        if axis == "heading":
            # Special handling for heading to handle wrap-around at 360°
            error = ((self.current_heading - setpoint + 180) % 360) - 180
        elif axis == "roll":
            error = self.current_roll - setpoint
        elif axis == "pitch":
            error = self.current_pitch - setpoint
        else:
            raise ValueError(f"Unknown axis: {axis}")
        return error
    
    def _apply_correction(self, axis, setpoint, kp):
        """Apply proportional correction to appropriate thrusters based on axis."""
        error = self._get_error(axis, setpoint)
        correction = kp * error
        
        # Clamp correction to safe range
        correction = max(min(correction, 0.5), -0.5)
        
        # Apply correction to appropriate thrusters based on axis
        if axis == "heading":
            # Apply to horizontal thrusters for rotation
            if self._using_diagonal_thrusters():
                # For 45° motor placement (diagonal thrusters)
                self.thrusters[0].set_speed(correction)   # Front Left
                self.thrusters[3].set_speed(correction)   # Back Right
                self.thrusters[1].set_speed(-correction)  # Front Right
                self.thrusters[2].set_speed(-correction)  # Back Left
            else:
                # For standard X configuration
                self.thrusters[0].set_speed(correction)   # Front Left
                self.thrusters[2].set_speed(correction)   # Back Left
                self.thrusters[1].set_speed(-correction)  # Front Right
                self.thrusters[3].set_speed(-correction)  # Back Right
                
        elif axis == "roll":
            # Apply opposite corrections to left/right vertical thrusters
            self.thrusters[4].set_speed(correction)   # FL Vertical
            self.thrusters[7].set_speed(correction)   # BL Vertical
            self.thrusters[5].set_speed(-correction)  # FR Vertical
            self.thrusters[6].set_speed(-correction)  # BR Vertical
            
        elif axis == "pitch":
            # Apply opposite corrections to front/back vertical thrusters
            self.thrusters[4].set_speed(correction)   # FL Vertical
            self.thrusters[5].set_speed(correction)   # FR Vertical
            self.thrusters[6].set_speed(-correction)  # BR Vertical
            self.thrusters[7].set_speed(-correction)  # BL Vertical
    
    def _using_diagonal_thrusters(self):
        """
        Check if we're using diagonal thruster configuration.
        This can be set via command line argument.
        """
        # Default to False unless explicitly set
        return getattr(self, 'diagonal_thrusters', False)
    
    def save_calibration(self):
        """Save calibration results to a JSON file."""
        try:
            with open(self.save_file, 'w') as f:
                json.dump(self.calibration_results, f, indent=2)
            logger.info(f"Calibration data saved to {self.save_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving calibration data: {e}")
            return False
    
    def run_calibration(self, axes=None, kp_start=0.05, kp_step=0.05, test_duration=15, max_tests=15):
        """Run full calibration sequence for specified axes."""
        if not axes:
            axes = ["heading", "roll", "pitch"]
        
        if not self.imu.available:
            logger.error("IMU not available - calibration cannot proceed")
            return False
        
        try:
            # Initialize hardware
            self.initialize_thrusters()
            self.start_orientation_thread()
            
            # Allow time for IMU to stabilize
            logger.info("Waiting for IMU readings to stabilize...")
            time.sleep(3.0)
            
            # Get initial calibration status
            cal_status = self.imu.get_calibration_status()
            logger.info(f"IMU calibration status: {cal_status}")
            
            # Run calibration for each specified axis
            calibration_success = True
            
            if "heading" in axes:
                logger.info("Starting heading calibration...")
                success = self.calibrate_heading(kp_start, kp_step, test_duration)
                calibration_success = calibration_success and success
                # Wait between calibrations
                time.sleep(3.0)
            
            if "roll" in axes:
                logger.info("Starting roll calibration...")
                success = self.calibrate_roll(kp_start, kp_step, test_duration)
                calibration_success = calibration_success and success
                # Wait between calibrations
                time.sleep(3.0)
            
            if "pitch" in axes:
                logger.info("Starting pitch calibration...")
                success = self.calibrate_pitch(kp_start, kp_step, test_duration)
                calibration_success = calibration_success and success
            
            # Save results regardless of success (may have partial success)
            self.save_calibration()
            
            # Print final results
            logger.info("\n" + "="*50)
            logger.info("CALIBRATION RESULTS:")
            logger.info(f"Heading PID: Kp={self.calibration_results['heading_pid']['Kp']:.4f}, " +
                       f"Ki={self.calibration_results['heading_pid']['Ki']:.4f}, " +
                       f"Kd={self.calibration_results['heading_pid']['Kd']:.4f}")
            logger.info(f"Roll PID: Kp={self.calibration_results['roll_pid']['Kp']:.4f}, " +
                       f"Ki={self.calibration_results['roll_pid']['Ki']:.4f}, " +
                       f"Kd={self.calibration_results['roll_pid']['Kd']:.4f}")
            logger.info(f"Pitch PID: Kp={self.calibration_results['pitch_pid']['Kp']:.4f}, " +
                       f"Ki={self.calibration_results['pitch_pid']['Ki']:.4f}, " +
                       f"Kd={self.calibration_results['pitch_pid']['Kd']:.4f}")
            logger.info("="*50 + "\n")
            
            return calibration_success
        
        except KeyboardInterrupt:
            logger.info("Calibration interrupted by user")
            return False
        except Exception as e:
            logger.error(f"Error during calibration: {e}")
            return False
        finally:
            # Clean up
            self.stop_thrusters()
            self.orientation_running = False
            if self.orientation_thread and self.orientation_thread.is_alive():
                self.orientation_thread.join(timeout=1.0)
            
            # Close hardware
            self.pca.deinit()
            if self.imu.available:
                self.imu.close()
    
# Handle SIGINT gracefully
def signal_handler(sig, frame):
    logger.info("Interrupted by user, shutting down...")
    sys.exit(0)

# Main function
def main():
    import sys
    signal.signal(signal.SIGINT, signal_handler)
    
    parser = argparse.ArgumentParser(description='PID Calibration using Ziegler-Nichols method')
    parser.add_argument('--axes', type=str, default='all',
                        help='Axes to calibrate (heading,roll,pitch or all)')
    parser.add_argument('--file', type=str, default='pid_auto_calibration.json',
                        help='Output file for calibration data')
    parser.add_argument('--kp-start', type=float, default=0.05,
                        help='Starting Kp value for calibration')
    parser.add_argument('--kp-step', type=float, default=0.05,
                        help='Step size for increasing Kp during calibration')
    parser.add_argument('--duration', type=int, default=15,
                        help='Test duration in seconds for each Kp value')
    parser.add_argument('--diagonal-thrusters', action='store_true',
                        help='Use diagonal thruster configuration (45° placement)')
    parser.add_argument('--log-level', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')
    # Add to argument parser in main():
    parser.add_argument('--max-tests', type=int, default=15,
                        help='Maximum number of Kp values to test')
        
    args = parser.parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(args.log_level)
    
    # Determine which axes to calibrate
    if args.axes.lower() == 'all':
        axes = ["heading", "roll", "pitch"]
    else:
        axes = [axis.strip().lower() for axis in args.axes.split(',')]
        valid_axes = ["heading", "roll", "pitch"]
        axes = [axis for axis in axes if axis in valid_axes]
        if not axes:
            logger.error("No valid axes specified")
            return
    
    logger.info(f"Starting calibration for: {', '.join(axes)}")
    
    # Create calibrator
    calibrator = PIDCalibrator(save_file=args.file)
    
    # Set diagonal thrusters configuration if specified
    calibrator.diagonal_thrusters = args.diagonal_thrusters
    
    # Begin interactive calibration
    print("\n" + "="*60)
    print("PID CALIBRATION USING ZIEGLER-NICHOLS METHOD")
    print("="*60)
    print("\nWARNING: This will cause the ROV to move. Ensure it has")
    print("sufficient space and is properly secured in water.")
    print("\nPress Ctrl+C at any time to abort the calibration.\n")
    
    input("Press Enter to begin calibration, or Ctrl+C to cancel...")
    
        # Then pass it to the calibration method:
    success = calibrator.run_calibration(
        axes=axes,
        kp_start=args.kp_start,
        kp_step=args.kp_step,
        test_duration=args.duration,
        max_tests=args.max_tests  # Add this line
    )
    
    if success:
        print("\nCalibration completed successfully!")
    else:
        print("\nCalibration completed with some issues. Check the log for details.")
    
    print(f"Results saved to: {args.file}")

if __name__ == "__main__":
    main()

# python ZieglerCalibration.py --kp-start 0.1 --kp-step 0.1 --duration 8 --max-tests 8 --axes heading