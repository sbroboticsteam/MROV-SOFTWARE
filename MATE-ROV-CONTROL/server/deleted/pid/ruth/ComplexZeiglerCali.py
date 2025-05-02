import time
import json
import signal
import logging
import argparse
import threading
import numpy as np
from datetime import datetime
import os
import sys

# Import ROV components
from rov.hardware.pca9685 import PCA9685
from classesForChatPID.thruster import Thruster
from classesForChatPID.imu_sensor import IMUSensor
from rov.ethernet_manager import EthernetManager

# Configure logging
log_file = f"pid_calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()]
)
logger = logging.getLogger("PID_Calibration")

class PIDCalibrator:
    """Enhanced class for calibrating PID controllers using modified Ziegler-Nichols method."""
    
    def __init__(self, save_file="pid_auto_calibration.json", tuning_factor=1.0, interactive=True):
        logger.info("Initializing PID calibrator")
        
        # Save file path
        self.save_file = save_file
        self.tuning_factor = tuning_factor
        self.interactive = interactive
        
        # Initialize PCA9685 PWM controller and thrusters
        try:
            self.pca = PCA9685(bus_number=7)
            self.pca.frequency = 50  # 50Hz for ESCs
        except Exception as e:
            logger.error(f"Failed to initialize PWM controller: {e}")
            raise RuntimeError("PWM controller initialization failed")
        
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
        
        # Calibration metadata
        self.calibration_metadata = {
            "timestamp": datetime.now().isoformat(),
            "tuning_factor": tuning_factor,
            "thruster_config": "diagonal" if getattr(self, 'diagonal_thrusters', False) else "standard"
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
        """Initialize all thruster ESCs with safety checks."""
        logger.info("Initializing all thrusters...")
        
        init_success = True
        for thruster in self.thrusters:
            try:
                thruster.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize thruster {thruster.name}: {e}")
                init_success = False
        
        if init_success:
            logger.info("All thrusters initialized successfully")
        else:
            logger.warning("Some thrusters failed to initialize")
            
        # Wait for ESCs to be fully initialized
        time.sleep(2.0)
        return init_success
    
    def stop_thrusters(self):
        """Stop all thrusters with safety verification."""
        logger.info("Stopping all thrusters...")
        
        for thruster in self.thrusters:
            try:
                thruster.stop()
            except Exception as e:
                logger.error(f"Error stopping thruster {thruster.name}: {e}")
        
        # Double-check all thrusters are stopped
        time.sleep(0.5)
        for thruster in self.thrusters:
            try:
                thruster.stop()  # Second stop command for safety
            except:
                pass
                
        logger.info("All thrusters stopped")
    
    def calibrate_heading(self, kp_start=0.05, kp_step=0.05, test_duration=15):
        """Calibrate heading PID using modified Ziegler-Nichols method."""
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
            # Calculate PID parameters using modified Ziegler-Nichols formula
            kp, ki, kd = self._calculate_pid_values(ultimate_gain, oscillation_period)
            
            self.calibration_results["heading_pid"]["Kp"] = kp
            self.calibration_results["heading_pid"]["Ki"] = ki
            self.calibration_results["heading_pid"]["Kd"] = kd
            
            logger.info(f"Heading PID calibration complete: Kp={kp:.4f}, Ki={ki:.4f}, Kd={kd:.4f}")
            
            # Validate the calculated PID values
            if self.interactive and input("Validate heading PID values? (y/n): ").lower() == 'y':
                self._validate_pid("heading", kp, ki, kd)
        else:
            logger.warning("Heading calibration did not yield valid results")
        
        self.current_calibration = None
        return ultimate_gain is not None
    
    def calibrate_roll(self, kp_start=0.05, kp_step=0.05, test_duration=15):
        """Calibrate roll PID using modified Ziegler-Nichols method."""
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
            # Calculate PID parameters using modified Ziegler-Nichols formula
            kp, ki, kd = self._calculate_pid_values(ultimate_gain, oscillation_period)
            
            self.calibration_results["roll_pid"]["Kp"] = kp
            self.calibration_results["roll_pid"]["Ki"] = ki
            self.calibration_results["roll_pid"]["Kd"] = kd
            
            logger.info(f"Roll PID calibration complete: Kp={kp:.4f}, Ki={ki:.4f}, Kd={kd:.4f}")
            
            # Validate the calculated PID values
            if self.interactive and input("Validate roll PID values? (y/n): ").lower() == 'y':
                self._validate_pid("roll", kp, ki, kd)
        else:
            logger.warning("Roll calibration did not yield valid results")
        
        self.current_calibration = None
        return ultimate_gain is not None
    
    def calibrate_pitch(self, kp_start=0.05, kp_step=0.05, test_duration=15):
        """Calibrate pitch PID using modified Ziegler-Nichols method."""
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
            # Calculate PID parameters using modified Ziegler-Nichols formula
            kp, ki, kd = self._calculate_pid_values(ultimate_gain, oscillation_period)
            
            self.calibration_results["pitch_pid"]["Kp"] = kp
            self.calibration_results["pitch_pid"]["Ki"] = ki
            self.calibration_results["pitch_pid"]["Kd"] = kd
            
            logger.info(f"Pitch PID calibration complete: Kp={kp:.4f}, Ki={ki:.4f}, Kd={kd:.4f}")
            
            # Validate the calculated PID values
            if self.interactive and input("Validate pitch PID values? (y/n): ").lower() == 'y':
                self._validate_pid("pitch", kp, ki, kd)
        else:
            logger.warning("Pitch calibration did not yield valid results")
        
        self.current_calibration = None
        return ultimate_gain is not None
    
    def _calculate_pid_values(self, ultimate_gain, oscillation_period):
        """Calculate PID values using Ziegler-Nichols method with tuning factor."""
        # Classic Ziegler-Nichols PID values
        kp = 0.6 * ultimate_gain * self.tuning_factor
        ki = 1.2 * ultimate_gain / oscillation_period * self.tuning_factor
        kd = 0.075 * ultimate_gain * oscillation_period * self.tuning_factor
        
        return kp, ki, kd
    
    def _validate_pid(self, axis, kp, ki, kd, test_duration=15):
        """Validate PID values by running a full PID controller and measuring performance."""
        logger.info(f"Validating {axis} PID values: Kp={kp:.4f}, Ki={ki:.4f}, Kd={kd:.4f}")
        
        # Get setpoint
        if axis == "heading":
            with self.orientation_lock:
                setpoint = self.current_heading
        else:
            setpoint = 0  # Level for roll and pitch
        
        # Reset data collection
        self.data_collection[axis]["values"] = []
        self.data_collection[axis]["times"] = []
        self.data_collection[axis]["setpoint"] = setpoint
        
        # Variables for PID controller
        integral = 0
        last_error = 0
        start_time = time.time()
        
        try:
            while time.time() - start_time < test_duration:
                # Get current error
                error = self._get_error(axis, setpoint)
                
                # Calculate PID components
                integral += error * 0.01  # dt ≈ 0.01s
                derivative = (error - last_error) / 0.01
                
                # Calculate correction
                correction = kp * error + ki * integral + kd * derivative
                correction = max(min(correction, 0.5), -0.5)  # Limit output
                
                # Apply correction
                self._apply_correction(axis, setpoint, correction)
                
                # Record data
                with self.orientation_lock:
                    if axis == "heading":
                        self.data_collection[axis]["values"].append(self.current_heading)
                    elif axis == "roll":
                        self.data_collection[axis]["values"].append(self.current_roll)
                    elif axis == "pitch":
                        self.data_collection[axis]["values"].append(self.current_pitch)
                    self.data_collection[axis]["times"].append(time.time())
                
                # Update for next iteration
                last_error = error
                time.sleep(0.01)
                
            # Stop thrusters
            self.stop_thrusters()
            
            # Calculate performance metrics
            self._calculate_performance_metrics(axis)
            
        except Exception as e:
            logger.error(f"Error during PID validation: {e}")
        finally:
            self.stop_thrusters()
    
    def _calculate_performance_metrics(self, axis):
        """Calculate performance metrics for PID validation."""
        if not self.data_collection[axis]["values"]:
            logger.warning(f"No data collected for {axis} validation")
            return
            
        values = np.array(self.data_collection[axis]["values"])
        setpoint = self.data_collection[axis]["setpoint"]
        
        # Calculate error for each point
        if axis == "heading":
            # Handle heading wraparound
            errors = np.array([
                ((val - setpoint + 180) % 360 - 180) for val in values
            ])
        else:
            errors = values - setpoint
            
        # Calculate metrics
        mean_error = np.mean(np.abs(errors))
        max_error = np.max(np.abs(errors))
        std_error = np.std(errors)
        
        logger.info(f"{axis.capitalize()} PID Performance Metrics:")
        logger.info(f"  Mean absolute error: {mean_error:.2f}°")
        logger.info(f"  Maximum error: {max_error:.2f}°")
        logger.info(f"  Standard deviation: {std_error:.2f}°")
        
        # Evaluate performance
        if mean_error < 5.0 and max_error < 15.0:
            logger.info(f"{axis.capitalize()} PID performance is good")
        elif mean_error < 10.0 and max_error < 25.0:
            logger.info(f"{axis.capitalize()} PID performance is acceptable")
        else:
            logger.warning(f"{axis.capitalize()} PID performance needs improvement")
            
        # Save validation data for analysis
        self._save_validation_data(axis, errors)
    
    def _save_validation_data(self, axis, errors):
        """Save validation data for later analysis."""
        validation_file = f"{axis}_pid_validation.json"
        try:
            validation_data = {
                "times": self.data_collection[axis]["times"],
                "values": self.data_collection[axis]["values"],
                "setpoint": self.data_collection[axis]["setpoint"],
                "errors": errors.tolist(),
                "pid": self.calibration_results[f"{axis}_pid"]
            }
            
            with open(validation_file, 'w') as f:
                json.dump(validation_data, f, indent=2)
                
            logger.info(f"Validation data saved to {validation_file}")
        except Exception as e:
            logger.error(f"Error saving validation data: {e}")
    
    def _perform_ziegler_nichols(self, axis, setpoint, kp_start, kp_step, max_duration, max_tests=15):
        """
        Perform Ziegler-Nichols ultimate gain test for the specified axis with enhanced
        oscillation detection.
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
        test_count = 0
        
        # Adaptive step size based on initial response
        adaptive_step = False
        last_response_magnitude = 0
        
        try:
            # Test progressively higher Kp values
            while test_count < max_tests and not ultimate_gain:
                logger.info(f"Testing Kp={current_kp:.4f} for {axis}")
                
                # Reset test data for this Kp value
                self.data_collection[axis]["values"] = []
                self.data_collection[axis]["times"] = []
                zero_crossings = []
                peak_times = []
                peak_values = []
                
                # Start time for this test
                start_time = time.time()
                
                # Variables for oscillation detection
                prev_error = 0
                prev_deriv = 0
                
                # Apply first correction
                self._apply_correction(axis, setpoint, current_kp)
                
                # Monitor system response for this Kp value
                while time.time() - start_time < max_duration:
                    # Apply P-only controller correction
                    self._apply_correction(axis, setpoint, current_kp)
                    
                    # Calculate current error
                    current_error = self._get_error(axis, setpoint)
                    
                    # Estimate derivative of error
                    current_deriv = current_error - prev_error
                    
                    # Detect zero crossings (error sign change)
                    if prev_error * current_error < 0:
                        zero_crossings.append(time.time())
                    
                    # Detect peaks (derivative sign change from positive to negative)
                    if prev_deriv > 0 and current_deriv <= 0:
                        peak_times.append(time.time())
                        peak_values.append(abs(current_error))
                    
                    prev_error = current_error
                    prev_deriv = current_deriv
                    
                    # Safety check - stop if limits exceeded
                    if check_safety_limits():
                        logger.warning(f"Safety limit exceeded for {axis}. Stopping test.")
                        self.stop_thrusters()
                        time.sleep(2)  # Wait for system to stabilize
                        break
                    
                    # Enhanced oscillation detection with multiple criteria
                    if len(zero_crossings) >= 6 and len(peak_values) >= 3:  # At least 3 full oscillations
                        # Calculate periods from zero crossings
                        z_periods = []
                        for i in range(2, len(zero_crossings)):
                            period = (zero_crossings[i] - zero_crossings[i-2])
                            z_periods.append(period)
                        
                        # Calculate periods from peaks
                        p_periods = []
                        for i in range(1, len(peak_times)):
                            period = (peak_times[i] - peak_times[i-1]) * 2
                            p_periods.append(period)
                        
                        # Calculate average period and check consistency
                        if z_periods and p_periods:
                            # Use peak-based periods as they're typically more accurate
                            avg_period = sum(p_periods) / len(p_periods)
                            period_stddev = np.std(p_periods)
                            
                            # Check amplitude consistency
                            amplitude_stddev = np.std(peak_values[-3:])
                            amplitude_mean = np.mean(peak_values[-3:])
                            
                            # Sustained oscillations criteria:
                            # 1. Low period variance (consistent frequency)
                            # 2. Low amplitude variance (consistent amplitude)
                            if (period_stddev < 0.2 * avg_period and 
                                amplitude_stddev < 0.3 * amplitude_mean):
                                logger.info(f"Sustained oscillations detected with Kp={current_kp:.4f}, "
                                          f"period={avg_period:.3f}s, amplitude={amplitude_mean:.3f}°")
                                ultimate_gain = current_kp
                                oscillation_period = avg_period
                                break
                    
                    # Prevent CPU hogging
                    time.sleep(0.02)
                
                # Adaptive step size adjustment
                if peak_values:
                    current_response_magnitude = max(peak_values)
                    
                    # If response is very small, use larger step
                    if current_response_magnitude < 2.0:
                        kp_step = kp_step * 2.0
                        logger.info(f"Small response detected, increasing step size to {kp_step:.4f}")
                    # If response is large but no oscillations, use smaller step
                    elif current_response_magnitude > 15.0 and not adaptive_step:
                        kp_step = kp_step * 0.5
                        adaptive_step = True
                        logger.info(f"Large response detected, reducing step size to {kp_step:.4f}")
                    
                    last_response_magnitude = current_response_magnitude
                
                # If no sustained oscillations detected, increase Kp
                if not ultimate_gain:
                    # Stop thrusters between tests
                    self.stop_thrusters()
                    time.sleep(1.5)  # Wait for system to stabilize
                    
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
    
    def _apply_correction(self, axis, setpoint, correction_value):
        """
        Apply correction to appropriate thrusters based on axis.
        
        For diagonal thrusters, applies appropriate mixing based on thruster configuration.
        """
        # Determine if this is a PID correction (float) or a proportional correction (using Kp)
        if isinstance(correction_value, float):
            # Direct correction value (from PID)
            correction = correction_value
        else:
            # Calculate correction from proportional gain
            error = self._get_error(axis, setpoint)
            correction = correction_value * error
        
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
        """Check if we're using diagonal thruster configuration."""
        return getattr(self, 'diagonal_thrusters', False)
    
    def save_calibration(self):
        """Save calibration results to a JSON file with metadata."""
        try:
            # Add metadata to calibration results
            full_results = {
                "pid_values": self.calibration_results,
                "metadata": self.calibration_metadata
            }
            
            # Create a backup of previous calibration if it exists
            if os.path.exists(self.save_file):
                backup_file = f"{self.save_file}.bak"
                try:
                    with open(self.save_file, 'r') as src, open(backup_file, 'w') as dst:
                        dst.write(src.read())
                    logger.info(f"Backup created at {backup_file}")
                except Exception as e:
                    logger.warning(f"Failed to create backup: {e}")
            
            # Save new calibration
            with open(self.save_file, 'w') as f:
                json.dump(full_results, f, indent=2)
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
            if not self.initialize_thrusters():
                logger.error("Failed to initialize thrusters - aborting calibration")
                return False
                
            self.start_orientation_thread()
            
            # Allow time for IMU to stabilize
            logger.info("Waiting for IMU readings to stabilize...")
            time.sleep(3.0)
            
            # Get initial calibration status
            cal_status = self.imu.get_calibration_status()
            logger.info(f"IMU calibration status: {cal_status}")
            
            # Update metadata
            self.calibration_metadata["thruster_config"] = "diagonal" if self._using_diagonal_thrusters() else "standard"
            self.calibration_metadata["timestamp"] = datetime.now().isoformat()
            
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
            
            # Run coupled-axis validation if all axes calibrated
            if calibration_success and len(axes) > 1 and self.interactive:
                if input("\nRun coupled-axis validation? (y/n): ").lower() == 'y':
                    self._validate_coupled_axes(test_duration=10)
            
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
            try:
                self.pca.deinit()
            except:
                pass
                
            if self.imu.available:
                try:
                    self.imu.close()
                except:
                    pass
    
    def _validate_coupled_axes(self, test_duration=10):
        """Validate how well the calibrated PID controllers handle multiple axes simultaneously."""
        logger.info("Running coupled-axis validation test")
        
        # Get PID values
        heading_pid = self.calibration_results["heading_pid"]
        roll_pid = self.calibration_results["roll_pid"]
        pitch_pid = self.calibration_results["pitch_pid"]
        
        # Get current orientation as setpoint for heading
        with self.orientation_lock:
            heading_setpoint = self.current_heading
        
        # Use 0 as setpoint for roll and pitch
        roll_setpoint = 0
        pitch_setpoint = 0
        
        # Variables for PID controllers
        heading_integral = roll_integral = pitch_integral = 0
        heading_last_error = roll_last_error = pitch_last_error = 0
        
        # Data for validation
        coupled_data = {
            "heading": {"values": [], "times": [], "setpoint": heading_setpoint},
            "roll": {"values": [], "times": [], "setpoint": roll_setpoint},
            "pitch": {"values": [], "times": [], "setpoint": pitch_setpoint}
        }
        
        start_time = time.time()
        last_time = start_time
        
        try:
            logger.info("Starting coupled-axis test with all PIDs active...")
            
            while time.time() - start_time < test_duration:
                current_time = time.time()
                dt = current_time - last_time
                last_time = current_time
                
                # Get current errors
                with self.orientation_lock:
                    heading_error = ((self.current_heading - heading_setpoint + 180) % 360) - 180
                    roll_error = self.current_roll - roll_setpoint
                    pitch_error = self.current_pitch - pitch_setpoint
                    
                    # Record data
                    coupled_data["heading"]["values"].append(self.current_heading)
                    coupled_data["heading"]["times"].append(current_time)
                    coupled_data["roll"]["values"].append(self.current_roll)
                    coupled_data["roll"]["times"].append(current_time)
                    coupled_data["pitch"]["values"].append(self.current_pitch)
                    coupled_data["pitch"]["times"].append(current_time)
                
                # Update integrals with anti-windup
                heading_integral = max(min(heading_integral + heading_error * dt, 10), -10)
                roll_integral = max(min(roll_integral + roll_error * dt, 10), -10)
                pitch_integral = max(min(pitch_integral + pitch_error * dt, 10), -10)
                
                # Calculate derivatives
                heading_derivative = (heading_error - heading_last_error) / max(dt, 0.001)
                roll_derivative = (roll_error - roll_last_error) / max(dt, 0.001)
                pitch_derivative = (pitch_error - pitch_last_error) / max(dt, 0.001)
                
                # Calculate PID outputs
                heading_output = (
                    heading_pid["Kp"] * heading_error +
                    heading_pid["Ki"] * heading_integral +
                    heading_pid["Kd"] * heading_derivative
                )
                
                roll_output = (
                    roll_pid["Kp"] * roll_error +
                    roll_pid["Ki"] * roll_integral +
                    roll_pid["Kd"] * roll_derivative
                )
                
                pitch_output = (
                    pitch_pid["Kp"] * pitch_error +
                    pitch_pid["Ki"] * pitch_integral +
                    pitch_pid["Kd"] * pitch_derivative
                )
                
                # Limit outputs
                heading_output = max(min(heading_output, 0.5), -0.5)
                roll_output = max(min(roll_output, 0.5), -0.5)
                pitch_output = max(min(pitch_output, 0.5), -0.5)
                
                # Apply corrections (mixed appropriately for each thruster)
                self._apply_mixed_corrections(heading_output, roll_output, pitch_output)
                
                # Update last errors
                heading_last_error = heading_error
                roll_last_error = roll_error
                pitch_last_error = pitch_error
                
                # Sleep to maintain control rate
                time.sleep(0.01)
                
            # Stop thrusters
            self.stop_thrusters()
            
            # Calculate and report validation results
            self._report_coupled_validation_results(coupled_data)
            
        except Exception as e:
            logger.error(f"Error during coupled validation: {e}")
        finally:
            self.stop_thrusters()
    
    def _apply_mixed_corrections(self, heading, roll, pitch):
        """Apply mixed corrections to thrusters for multiple axes."""
        # For horizontal thrusters (0-3), mix heading with a small amount of roll/pitch compensation
        if self._using_diagonal_thrusters():
            # Diagonal thruster configuration
            self.thrusters[0].set_speed(heading + 0.2 * roll)        # Front Left
            self.thrusters[1].set_speed(-heading - 0.2 * roll)       # Front Right
            self.thrusters[2].set_speed(-heading + 0.2 * roll)       # Back Left
            self.thrusters[3].set_speed(heading - 0.2 * roll)        # Back Right
        else:
            # Standard X configuration
            self.thrusters[0].set_speed(heading + 0.2 * roll)        # Front Left
            self.thrusters[1].set_speed(-heading - 0.2 * roll)       # Front Right
            self.thrusters[2].set_speed(heading + 0.2 * roll)        # Back Left
            self.thrusters[3].set_speed(-heading - 0.2 * roll)       # Back Right
        
        # For vertical thrusters (4-7), mix roll and pitch
        self.thrusters[4].set_speed(roll + pitch)       # Front Left Up
        self.thrusters[5].set_speed(-roll + pitch)      # Front Right Up
        self.thrusters[6].set_speed(-roll - pitch)      # Back Right Up
        self.thrusters[7].set_speed(roll - pitch)       # Back Left Up
    
    def _report_coupled_validation_results(self, data):
        """Report results of coupled validation test."""
        try:
            # Calculate stats for each axis
            heading_values = np.array(data["heading"]["values"])
            roll_values = np.array(data["roll"]["values"])
            pitch_values = np.array(data["pitch"]["values"])
            
            # Calculate errors
            heading_errors = np.array([
                ((val - data["heading"]["setpoint"] + 180) % 360 - 180) 
                for val in heading_values
            ])
            roll_errors = roll_values - data["roll"]["setpoint"]
            pitch_errors = pitch_values - data["pitch"]["setpoint"]
            
            # Calculate metrics
            metrics = {
                "heading": {
                    "mean_error": np.mean(np.abs(heading_errors)),
                    "max_error": np.max(np.abs(heading_errors)),
                    "std_dev": np.std(heading_errors)
                },
                "roll": {
                    "mean_error": np.mean(np.abs(roll_errors)),
                    "max_error": np.max(np.abs(roll_errors)),
                    "std_dev": np.std(roll_errors)
                },
                "pitch": {
                    "mean_error": np.mean(np.abs(pitch_errors)),
                    "max_error": np.max(np.abs(pitch_errors)),
                    "std_dev": np.std(pitch_errors)
                }
            }
            
            # Report results
            logger.info("\n" + "="*50)
            logger.info("COUPLED VALIDATION RESULTS:")
            for axis in ["heading", "roll", "pitch"]:
                logger.info(f"{axis.capitalize()}:")
                logger.info(f"  Mean absolute error: {metrics[axis]['mean_error']:.2f}°")
                logger.info(f"  Maximum error: {metrics[axis]['max_error']:.2f}°")
                logger.info(f"  Standard deviation: {metrics[axis]['std_dev']:.2f}°")
            logger.info("="*50 + "\n")
            
            # Save validation data
            validation_file = "coupled_validation.json"
            validation_data = {
                "data": data,
                "metrics": metrics,
                "pid_values": self.calibration_results
            }
            
            with open(validation_file, 'w') as f:
                json.dump(validation_data, f, indent=2)
                
            logger.info(f"Coupled validation data saved to {validation_file}")
            
            # Provide assessment of coupling effects
            coupling_score = 0
            if metrics["heading"]["mean_error"] < 5.0:
                coupling_score += 1
            if metrics["roll"]["mean_error"] < 5.0:
                coupling_score += 1
            if metrics["pitch"]["mean_error"] < 5.0:
                coupling_score += 1
                
            if coupling_score == 3:
                logger.info("Assessment: PID controllers handle coupling effects well")
            elif coupling_score == 2:
                logger.info("Assessment: PID controllers handle coupling effects adequately")
            else:
                logger.info("Assessment: PID controllers may need adjustment for coupling effects")
                
        except Exception as e:
            logger.error(f"Error calculating validation results: {e}")
    
# Handle SIGINT gracefully
def signal_handler(sig, frame):
    logger.info("Interrupted by user, shutting down...")
    sys.exit(0)

# Main function
def main():
    signal.signal(signal.SIGINT, signal_handler)
    
    parser = argparse.ArgumentParser(description='Enhanced PID Calibration using Modified Ziegler-Nichols method')
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
    parser.add_argument('--tuning-factor', type=float, default=1.0,
                        help='Tuning factor for PID values (>1 more aggressive, <1 more conservative)')
    parser.add_argument('--non-interactive', action='store_true',
                        help='Run in non-interactive mode (no validation prompts)')
    parser.add_argument('--max-tests', type=int, default=15,
                        help='Maximum number of Kp values to test')
    parser.add_argument('--log-level', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')
        
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
    logger.info(f"Using tuning factor: {args.tuning_factor}")
    
    # Create calibrator
    calibrator = PIDCalibrator(
        save_file=args.file,
        tuning_factor=args.tuning_factor,
        interactive=not args.non_interactive
    )
    
    # Set diagonal thrusters configuration if specified
    calibrator.diagonal_thrusters = args.diagonal_thrusters
    logger.info(f"Using {'diagonal' if args.diagonal_thrusters else 'standard'} thruster configuration")
    
    # Begin calibration
    print("\n" + "="*60)
    print("ENHANCED PID CALIBRATION USING MODIFIED ZIEGLER-NICHOLS METHOD")
    print("="*60)
    print("\nWARNING: This will cause the ROV to move. Ensure it has")
    print("sufficient space and is properly secured in water.")
    print("\nPress Ctrl+C at any time to abort the calibration.\n")
    
    if not args.non_interactive:
        input("Press Enter to begin calibration, or Ctrl+C to cancel...")
    
    success = calibrator.run_calibration(
        axes=axes,
        kp_start=args.kp_start,
        kp_step=args.kp_step,
        test_duration=args.duration,
        max_tests=args.max_tests
    )
    
    if success:
        print("\nCalibration completed successfully!")
    else:
        print("\nCalibration completed with some issues. Check the log for details.")
    
    print(f"Results saved to: {args.file}")
    print(f"Log saved to: {log_file}")

if __name__ == "__main__":
    main()

# python ComplexZeiglerCali.py --diagonal-thrusters --tuning-factor 0.8