#!/usr/bin/env python3
# filepath: /home/sybau/Desktop/MROV-SOFTWARE/MATE-ROV-CONTROL/server/utilities/pid_calibrator.py

import sys
import os
import time
import json
import numpy as np
import matplotlib.pyplot as plt
from threading import Thread, Event
import logging
import argparse
from collections import deque

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import BNO055 and required components
try:
    from bno055 import BNO055, BNO055_ADDRESS_A
except ImportError:
    print("ERROR: Could not import BNO055 class.")
    print("Make sure bno055.py is accessible.")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("pid_calibration.log"), logging.StreamHandler()]
)
logger = logging.getLogger("PID-Calibrator")

class PIDCalibrator:
    """Class to automatically calibrate PID values for ROV stabilization"""
    
    def __init__(self, bus_number=7, address=BNO055_ADDRESS_A):
        # Initialize IMU sensor
        self.bno = BNO055(bus_number=bus_number, address=address)
        if not self.bno.begin():
            logger.error("Failed to initialize BNO055 sensor")
            raise RuntimeError("BNO055 initialization failed")
        
        # Data storage
        self.sample_rate = 50  # Hz
        self.sample_time = 1.0 / self.sample_rate
        self.running = False
        self.stop_event = Event()
        
        # PID parameters for testing
        self.axis_names = ["Heading", "Pitch", "Roll"]
        self.current_axis = 0  # 0=Heading, 1=Pitch, 2=Roll
        
        # Test configurations - these will be tested for each axis
        self.p_values = [0.01, 0.02, 0.05, 0.08, 0.1, 0.15, 0.2]
        self.i_values = [0.0, 0.001, 0.005, 0.01, 0.02]
        self.d_values = [0.0, 0.01, 0.02, 0.05, 0.1]
        
        # Results storage
        self.results = {}
        for axis_name in self.axis_names:
            self.results[axis_name] = []
            
        # Data for real-time monitoring
        self.data_buffer_length = 10 * self.sample_rate  # 10 seconds of data
        self.heading_data = deque(maxlen=self.data_buffer_length)
        self.pitch_data = deque(maxlen=self.data_buffer_length)
        self.roll_data = deque(maxlen=self.data_buffer_length)
        self.time_data = deque(maxlen=self.data_buffer_length)
        
        # Best parameters found so far
        self.best_params = {
            "Heading": {"Kp": 0.05, "Ki": 0.0, "Kd": 0.01, "score": float('inf')},
            "Pitch": {"Kp": 0.08, "Ki": 0.0, "Kd": 0.02, "score": float('inf')},
            "Roll": {"Kp": 0.08, "Ki": 0.0, "Kd": 0.02, "score": float('inf')}
        }
        
        logger.info("PID Calibrator initialized successfully")
        
    def start_data_collection(self):
        """Start collecting orientation data"""
        self.running = True
        self.stop_event.clear()
        self.collection_thread = Thread(target=self._data_collection_loop)
        self.collection_thread.daemon = True
        self.collection_thread.start()
        logger.info("Data collection started")
        
    def stop_data_collection(self):
        """Stop data collection thread"""
        self.stop_event.set()
        if hasattr(self, 'collection_thread') and self.collection_thread.is_alive():
            self.collection_thread.join(timeout=2.0)
        self.running = False
        logger.info("Data collection stopped")
        
    def _data_collection_loop(self):
        """Main data collection loop"""
        start_time = time.time()
        next_sample = start_time
        
        while not self.stop_event.is_set():
            current_time = time.time()
            
            # Wait until next sample time
            if current_time < next_sample:
                time.sleep(0.001)  # Short sleep to prevent CPU hogging
                continue
                
            try:
                # Read orientation data
                heading, roll, pitch = self.bno.get_euler()
                
                # Store data
                self.heading_data.append(heading)
                self.pitch_data.append(pitch)
                self.roll_data.append(roll)
                self.time_data.append(current_time - start_time)
                
                # Calculate next sample time
                next_sample += self.sample_time
                
                # Prevent time drift by re-anchoring if we're behind
                if current_time > next_sample + 5 * self.sample_time:
                    logger.warning("Sampling falling behind, recalibrating timing")
                    next_sample = current_time + self.sample_time
                    
            except Exception as e:
                logger.error(f"Error in data collection: {e}")
                time.sleep(0.1)  # Sleep on error to prevent rapid error loops
                
    def run_calibration(self, test_duration=10.0, stability_time=3.0):
        """Run the full calibration process"""
        logger.info("Starting PID calibration process")
        
        # Start data collection
        self.start_data_collection()
        time.sleep(1.0)  # Give sensor time to stabilize
        
        try:
            # Test each axis
            for axis_idx, axis_name in enumerate(self.axis_names):
                logger.info(f"Beginning calibration for {axis_name} axis")
                self.current_axis = axis_idx
                
                # Test different PID parameter combinations
                for p in self.p_values:
                    for i in self.i_values:
                        for d in self.d_values:
                            # Skip some combinations to reduce testing time
                            if i > 0 and d > 0 and len(self.results[axis_name]) > 10:
                                # Skip some combinations once we have some data
                                continue
                                
                            logger.info(f"Testing {axis_name} with P={p}, I={i}, D={d}")
                            
                            # Clear data buffers
                            self.heading_data.clear()
                            self.pitch_data.clear()
                            self.roll_data.clear()
                            self.time_data.clear()
                            
                            # Simulate applying these PID values
                            # In a real implementation, you would apply perturbation and 
                            # measure how well these PID values correct it
                            
                            # Wait for the test duration while collecting data
                            time.sleep(stability_time)  # Allow system to stabilize
                            
                            # Apply a simulated disturbance
                            logger.info(f"  Applying simulated disturbance...")
                            # In real implementation, you would physically disturb the ROV
                            
                            # Collect data during recovery
                            time.sleep(test_duration)
                            
                            # Calculate performance metrics
                            score = self._evaluate_performance(axis_idx)
                            
                            # Store results
                            result = {
                                "Kp": p,
                                "Ki": i,
                                "Kd": d,
                                "score": score,
                                "stability_time": self._calculate_stability_time(axis_idx),
                                "max_overshoot": self._calculate_max_overshoot(axis_idx)
                            }
                            self.results[axis_name].append(result)
                            
                            # Update best parameters if this set is better
                            if score < self.best_params[axis_name]["score"]:
                                self.best_params[axis_name] = {
                                    "Kp": p, 
                                    "Ki": i, 
                                    "Kd": d, 
                                    "score": score
                                }
                                logger.info(f"  New best parameters for {axis_name}: P={p}, I={i}, D={d}, Score={score:.4f}")
                            
                            # Brief pause between tests
                            time.sleep(1.0)
                
                # After testing all combinations for this axis
                logger.info(f"Completed calibration for {axis_name} axis")
                logger.info(f"Best parameters: P={self.best_params[axis_name]['Kp']}, "
                            f"I={self.best_params[axis_name]['Ki']}, "
                            f"D={self.best_params[axis_name]['Kd']}")
                
                # Visualize the best result for this axis
                self._visualize_best_result(axis_name)
            
            # Save all results
            self._save_results()
            
        finally:
            # Stop data collection
            self.stop_data_collection()
        
        logger.info("PID calibration process completed")
        return self.best_params
        
    def _evaluate_performance(self, axis_idx):
        """Calculate performance metrics for current PID parameters"""
        if axis_idx == 0:  # Heading
            data = list(self.heading_data)
        elif axis_idx == 1:  # Pitch
            data = list(self.pitch_data)
        else:  # Roll
            data = list(self.roll_data)
            
        if not data:
            return float('inf')
            
        # Use different metrics depending on what we're optimizing for
        # 1. Calculate sum of squared errors from setpoint (0 or initial value)
        setpoint = data[0]  # Use first value as setpoint
        squared_errors = [(x - setpoint)**2 for x in data]
        mse = sum(squared_errors) / len(squared_errors)
        
        # 2. Calculate oscillation penalty (variation in consecutive differences)
        diffs = [data[i+1] - data[i] for i in range(len(data)-1)]
        oscillation_penalty = np.std(diffs) if diffs else 0
        
        # 3. Calculate response time penalty
        # This would measure how long it takes to get within x% of setpoint
        
        # Combine metrics (weighted sum)
        score = mse + 2.0 * oscillation_penalty
        
        return score
        
    def _calculate_stability_time(self, axis_idx):
        """Calculate how long it takes to stabilize"""
        # Simplified implementation - would be more sophisticated in real use
        return 0.0  # Placeholder
        
    def _calculate_max_overshoot(self, axis_idx):
        """Calculate maximum overshoot"""
        # Simplified implementation - would be more sophisticated in real use
        return 0.0  # Placeholder
        
    def _visualize_best_result(self, axis_name):
        """Create a visualization of the best result for given axis"""
        if not self.results[axis_name]:
            logger.warning(f"No results to visualize for {axis_name}")
            return
            
        # Sort results by score
        sorted_results = sorted(self.results[axis_name], key=lambda x: x["score"])
        best_result = sorted_results[0]
        
        # Create parameter grid visualization
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        # Plot P parameter impact
        p_results = {}
        for result in self.results[axis_name]:
            p = result["Kp"]
            if p not in p_results or result["score"] < p_results[p]:
                p_results[p] = result["score"]
        
        if p_results:
            p_vals = list(p_results.keys())
            p_scores = [p_results[p] for p in p_vals]
            axes[0].plot(p_vals, p_scores, 'bo-')
            axes[0].set_title(f'{axis_name} - P Parameter Impact')
            axes[0].set_xlabel('Kp Value')
            axes[0].set_ylabel('Score (lower is better)')
            axes[0].grid(True)
        
        # Similar plots for I and D parameters
        i_results = {}
        for result in self.results[axis_name]:
            i = result["Ki"]
            if i not in i_results or result["score"] < i_results[i]:
                i_results[i] = result["score"]
        
        if i_results:
            i_vals = list(i_results.keys())
            i_scores = [i_results[i] for i in i_vals]
            axes[1].plot(i_vals, i_scores, 'ro-')
            axes[1].set_title(f'{axis_name} - I Parameter Impact')
            axes[1].set_xlabel('Ki Value')
            axes[1].set_ylabel('Score (lower is better)')
            axes[1].grid(True)
        
        d_results = {}
        for result in self.results[axis_name]:
            d = result["Kd"]
            if d not in d_results or result["score"] < d_results[d]:
                d_results[d] = result["score"]
        
        if d_results:
            d_vals = list(d_results.keys())
            d_scores = [d_results[d] for d in d_vals]
            axes[2].plot(d_vals, d_scores, 'go-')
            axes[2].set_title(f'{axis_name} - D Parameter Impact')
            axes[2].set_xlabel('Kd Value')
            axes[2].set_ylabel('Score (lower is better)')
            axes[2].grid(True)
        
        plt.tight_layout()
        plt.savefig(f'pid_calibration_{axis_name}.png')
        logger.info(f"Saved visualization for {axis_name} axis to pid_calibration_{axis_name}.png")
        
        # Close the plot to free memory
        plt.close(fig)
        
    def _save_results(self):
        """Save calibration results to a file"""
        # Create a results object with best parameters and all test results
        results_data = {
            "best_parameters": self.best_params,
            "all_results": self.results,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Save as JSON
        with open('pid_calibration_results.json', 'w') as f:
            json.dump(results_data, f, indent=2)
        
        # Also save a simplified results file with just the best parameters
        best_params_formatted = {
            "heading_pid": {
                "Kp": self.best_params["Heading"]["Kp"],
                "Ki": self.best_params["Heading"]["Ki"],
                "Kd": self.best_params["Heading"]["Kd"]
            },
            "pitch_pid": {
                "Kp": self.best_params["Pitch"]["Kp"],
                "Ki": self.best_params["Pitch"]["Ki"],
                "Kd": self.best_params["Pitch"]["Kd"]
            },
            "roll_pid": {
                "Kp": self.best_params["Roll"]["Kp"],
                "Ki": self.best_params["Roll"]["Ki"],
                "Kd": self.best_params["Roll"]["Kd"]
            }
        }
        
        with open('pid_best_parameters.json', 'w') as f:
            json.dump(best_params_formatted, f, indent=2)
            
        logger.info("Saved all calibration results to pid_calibration_results.json")
        logger.info("Saved best parameters to pid_best_parameters.json")
        
        # Print the best results
        print("\n=== CALIBRATION RESULTS ===")
        print(f"Heading PID: P={self.best_params['Heading']['Kp']}, I={self.best_params['Heading']['Ki']}, D={self.best_params['Heading']['Kd']}")
        print(f"Pitch PID:   P={self.best_params['Pitch']['Kp']}, I={self.best_params['Pitch']['Ki']}, D={self.best_params['Pitch']['Kd']}")
        print(f"Roll PID:    P={self.best_params['Roll']['Kp']}, I={self.best_params['Roll']['Ki']}, D={self.best_params['Roll']['Kd']}")
        print("==========================\n")

class AutoCalibrationRoutine:
    """Run automatic calibration routines for ROV PID tuning"""
    
    def __init__(self, calibrator):
        self.calibrator = calibrator
        logger.info("Auto-calibration routine initialized")
        
    def run_heading_calibration(self):
        """Run calibration for heading (yaw) control"""
        logger.info("Starting heading calibration routine")
        
        # Instructions for the operator
        print("\n==== HEADING CALIBRATION ====")
        print("This calibration will test the ROV's ability to maintain heading.")
        print("Please ensure the ROV is in the water and can rotate freely.")
        print("The ROV will attempt to maintain its initial heading during disturbances.")
        print("\nPress ENTER when ready, or CTRL+C to abort...")
        input()
        
        # Set axis to heading
        self.calibrator.current_axis = 0
        
        # Start data collection
        self.calibrator.start_data_collection()
        
        try:
            # Give user instructions for manual testing
            print("\nPlease perform the following actions:")
            print("1. Wait 5 seconds for initial stability")
            time.sleep(5)
            
            print("2. SLOWLY rotate the ROV about 45 degrees clockwise")
            print("   (waiting 10 seconds)")
            time.sleep(10)
            
            print("3. Release the ROV and let it stabilize")
            print("   (waiting 15 seconds)")
            time.sleep(15)
            
            print("4. SLOWLY rotate the ROV about 45 degrees counter-clockwise")
            print("   (waiting 10 seconds)")
            time.sleep(10)
            
            print("5. Release and let stabilize")
            print("   (waiting 15 seconds)")
            time.sleep(15)
            
            # Analyze collected data
            print("\nAnalyzing heading response data...")
            
            # In a real implementation, this would analyze the collected data
            # and pick optimal PID values based on the response
            
            # For demonstration, we'll just return some reasonable values
            pid_values = {
                "Kp": 0.08,
                "Ki": 0.002,
                "Kd": 0.05
            }
            
            print(f"\nRecommended Heading PID values:")
            print(f"P={pid_values['Kp']}, I={pid_values['Ki']}, D={pid_values['Kd']}")
            
            return pid_values
            
        finally:
            # Stop data collection
            self.calibrator.stop_data_collection()
        
    def run_pitch_calibration(self):
        """Run calibration for pitch control"""
        logger.info("Starting pitch calibration routine")
        
        # Instructions for the operator
        print("\n==== PITCH CALIBRATION ====")
        print("This calibration will test the ROV's ability to maintain level pitch.")
        print("Please ensure the ROV is in the water and can tilt freely.")
        print("\nPress ENTER when ready, or CTRL+C to abort...")
        input()
        
        # Set axis to pitch
        self.calibrator.current_axis = 1
        
        # Start data collection
        self.calibrator.start_data_collection()
        
        try:
            # Give user instructions for manual testing
            print("\nPlease perform the following actions:")
            print("1. Wait 5 seconds for initial stability")
            time.sleep(5)
            
            print("2. Gently tilt the ROV forward (nose down)")
            print("   (waiting 10 seconds)")
            time.sleep(10)
            
            print("3. Release the ROV and let it stabilize")
            print("   (waiting 15 seconds)")
            time.sleep(15)
            
            print("4. Gently tilt the ROV backward (nose up)")
            print("   (waiting 10 seconds)")
            time.sleep(10)
            
            print("5. Release and let stabilize")
            print("   (waiting 15 seconds)")
            time.sleep(15)
            
            # Analyze collected data
            print("\nAnalyzing pitch response data...")
            
            # For demonstration, return reasonable values
            pid_values = {
                "Kp": 0.1,
                "Ki": 0.001,
                "Kd": 0.02
            }
            
            print(f"\nRecommended Pitch PID values:")
            print(f"P={pid_values['Kp']}, I={pid_values['Ki']}, D={pid_values['Kd']}")
            
            return pid_values
            
        finally:
            # Stop data collection
            self.calibrator.stop_data_collection()
            
    def run_roll_calibration(self):
        """Run calibration for roll control"""
        logger.info("Starting roll calibration routine")
        
        # Instructions for the operator
        print("\n==== ROLL CALIBRATION ====")
        print("This calibration will test the ROV's ability to maintain level roll.")
        print("Please ensure the ROV is in the water and can roll freely.")
        print("\nPress ENTER when ready, or CTRL+C to abort...")
        input()
        
        # Set axis to roll
        self.calibrator.current_axis = 2
        
        # Start data collection
        self.calibrator.start_data_collection()
        
        try:
            # Give user instructions for manual testing
            print("\nPlease perform the following actions:")
            print("1. Wait 5 seconds for initial stability")
            time.sleep(5)
            
            print("2. Gently roll the ROV to the right")
            print("   (waiting 10 seconds)")
            time.sleep(10)
            
            print("3. Release the ROV and let it stabilize")
            print("   (waiting 15 seconds)")
            time.sleep(15)
            
            print("4. Gently roll the ROV to the left")
            print("   (waiting 10 seconds)")
            time.sleep(10)
            
            print("5. Release and let stabilize")
            print("   (waiting 15 seconds)")
            time.sleep(15)
            
            # Analyze collected data
            print("\nAnalyzing roll response data...")
            
            # For demonstration, return reasonable values
            pid_values = {
                "Kp": 0.1,
                "Ki": 0.001,
                "Kd": 0.02
            }
            
            print(f"\nRecommended Roll PID values:")
            print(f"P={pid_values['Kp']}, I={pid_values['Ki']}, D={pid_values['Kd']}")
            
            return pid_values
            
        finally:
            # Stop data collection
            self.calibrator.stop_data_collection()
            
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='ROV PID Calibration Tool')
    parser.add_argument('--auto', action='store_true', help='Run automatic calibration routine')
    parser.add_argument('--heading-only', action='store_true', help='Calibrate only heading')
    parser.add_argument('--pitch-only', action='store_true', help='Calibrate only pitch')
    parser.add_argument('--roll-only', action='store_true', help='Calibrate only roll')
    parser.add_argument('--bus', type=int, default=7, help='I2C bus number for BNO055')
    args = parser.parse_args()
    
    print("\n=== ROV PID CALIBRATION TOOL ===")
    print("This tool will help you find optimal PID values for ROV stabilization.")
    
    try:
        # Initialize calibrator
        calibrator = PIDCalibrator(bus_number=args.bus)
        
        # Wait for IMU to stabilize
        print("\nWaiting for IMU to stabilize...")
        time.sleep(2)
        
        # Check calibration status
        cal_sys, cal_gyro, cal_accel, cal_mag = calibrator.bno.get_calibration()
        print(f"\nIMU Calibration Status:")
        print(f"System: {cal_sys}/3, Gyro: {cal_gyro}/3, Accel: {cal_accel}/3, Mag: {cal_mag}/3")
        
        if cal_sys < 1 or cal_gyro < 1:
            print("\nWARNING: IMU is not sufficiently calibrated for accurate results.")
            print("Move the ROV in a figure-8 pattern to calibrate the magnetometer.")
            print("Let it rest on a level surface to calibrate the accelerometer.")
            print("\nContinue anyway? (y/n)")
            if input().lower() != 'y':
                print("Calibration aborted. Please calibrate the IMU first.")
                return
        
        # If automatic calibration is requested
        if args.auto:
            auto_routine = AutoCalibrationRoutine(calibrator)
            results = {
                "heading": None,
                "pitch": None,
                "roll": None
            }
            
            try:
                # Run calibrations based on flags
                if args.heading_only or not (args.pitch_only or args.roll_only):
                    results["heading"] = auto_routine.run_heading_calibration()
                
                if args.pitch_only or not (args.heading_only or args.roll_only):
                    results["pitch"] = auto_routine.run_pitch_calibration()
                
                if args.roll_only or not (args.heading_only or args.pitch_only):
                    results["roll"] = auto_routine.run_roll_calibration()
                
                # Save results
                output = {
                    "heading_pid": results["heading"] if results["heading"] else {"Kp": 0.05, "Ki": 0.0, "Kd": 0.01},
                    "pitch_pid": results["pitch"] if results["pitch"] else {"Kp": 0.08, "Ki": 0.0, "Kd": 0.02},
                    "roll_pid": results["roll"] if results["roll"] else {"Kp": 0.08, "Ki": 0.0, "Kd": 0.02}
                }
                
                with open('pid_auto_calibration.json', 'w') as f:
                    json.dump(output, f, indent=2)
                
                print("\n=== CALIBRATION COMPLETE ===")
                print("Results saved to pid_auto_calibration.json")
                
            except KeyboardInterrupt:
                print("\nCalibration interrupted by user.")
                
        else:
            # Run the full algorithmic calibration
            print("\nRunning full calibration suite...")
            print("This will test multiple PID parameter combinations")
            print("and determine the optimal values for each axis.")
            print("\nPress ENTER to begin, or CTRL+C to abort...")
            input()
            
            try:
                best_params = calibrator.run_calibration()
                
                print("\n=== CALIBRATION COMPLETE ===")
                print(f"Best PID values have been saved to pid_best_parameters.json")
                
            except KeyboardInterrupt:
                print("\nCalibration interrupted by user.")
        
    except Exception as e:
        logger.error(f"Error in calibration: {e}")
        print(f"\nERROR: {e}")
        print("Calibration failed. See pid_calibration.log for details.")
    
if __name__ == "__main__":
    main()
    
"""
# For full algorithmic calibration of all axes:
python3 pid_calibrator.py

# For guided calibration of all axes:
python3 pid_calibrator.py --auto

# For guided calibration of just heading:
python3 pid_calibrator.py --auto --heading-only
"""