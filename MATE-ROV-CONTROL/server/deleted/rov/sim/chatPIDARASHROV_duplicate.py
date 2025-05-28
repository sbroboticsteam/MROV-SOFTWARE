from smbus2 import SMBus
from time import sleep
import json
import time
import threading
import select
import logging
import argparse
from enum import Enum
import math
import numpy as np
import sys

from rov.hardware.pca9685 import PCA9685
from classesForChatPID.thruster import Thruster
from classesForChatPID.imu_sensor import IMUSensor
from rov.pid_controller import PID_Controller, ElapsedTime
from rov.pid_system import PIDSystem
from rov.ethernet_manager import EthernetManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

# --------------------------- ROV Class ---------------------------
class ROV:
    """ROV control system with PID stabilization using Arash's PID implementation."""
    
    def __init__(self, pid_enabled=True):
        logger.info("Initializing ROV with Arash's PID controllers...")
        
        # Initialize PCA9685 PWM controller
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50  # 50Hz is typical for ESCs
        
        # Initialize PIDSystem for thruster control
        self.pid_system = PIDSystem(self.pca)
        
        # Set PID gains
        # Using conservative values that can be tuned later
        self.pid_system.pid_roll = PID_Controller(0.08, 0.02, 0.0, 0.1)  # P, D, I, filter
        self.pid_system.pid_pitch = PID_Controller(0.08, 0.02, 0.0, 0.1)
        self.pid_system.pid_yaw = PID_Controller(0.05, 0.01, 0.0, 0.1)
        self.pid_system.pid_depth = PID_Controller(0.1, 0.02, 0.0, 0.1)
        
        # Save references to thrusters for convenience
        self.thrusters = self.pid_system.thrusters
        
        # Initialize IMU sensor
        self.imu = IMUSensor()
        self.orientation_thread = None
        self.orientation_running = False
        self.current_heading = 0
        self.current_roll = 0
        self.current_pitch = 0
        self.current_depth = 0
        
        # PID control flags
        self.pid_enabled = pid_enabled and self.imu.available
        self.pid_lock = threading.Lock()
        self.heading_pid_enabled = False
        self.target_heading = None
        
        # Set initial stabilization settings
        self.pid_system.enable_stabilization(self.pid_enabled)
        self.pid_system.toggle_axis_stabilization('yaw', False)
        self.pid_system.toggle_axis_stabilization('roll', True)
        self.pid_system.toggle_axis_stabilization('pitch', True)
        self.pid_system.toggle_axis_stabilization('z', False)
        
        # Network communication via EthernetManager
        self.ethernet = EthernetManager(control_ip='192.168.1.237', control_port=4891)
        self.ethernet.set_control_callback(self.process_command)  # Set callback for commands
        
        # Data processing
        self.base_motor_states = [0.0] * 8
        self.final_motor_states = [0.0] * 8
        self.running = False
        self.last_command_time = time.time()
        
        logger.info("ROV initialization complete")
        
        if self.pid_enabled:
            logger.info("PID stabilization is ENABLED")
        else:
            logger.info("PID stabilization is DISABLED")
    
    def log_debug_info(self):
        """Log detailed debug information about PID and motor states."""
        # Get PID telemetry
        telemetry = self.pid_system.get_telemetry()
        
        # Get axis stabilization status
        axis_status = telemetry["axis_stabilization"]
        
        # Format motor values for better readability
        base_motors = [f"{x:.2f}" for x in self.base_motor_states]
        final_motors = [f"{t['speed']:.2f}" for t in telemetry['thrusters']]
        
        # Create debug message
        debug_info = (
            f"\n=== ROV Debug Info ===\n"
            f"Orientation: Heading={self.current_heading:.1f}° Roll={self.current_roll:.1f}° Pitch={self.current_pitch:.1f}°\n"
            f"Target Heading: {self.target_heading:.1f}°\n"
            f"PID Enabled: {self.pid_enabled}\n"
            f"Heading PID Enabled: {axis_status['yaw']}\n"
            f"PID Errors: Heading={telemetry['pid_data']['yaw']['error']:.3f} "
            f"Pitch={telemetry['pid_data']['pitch']['error']:.3f} "
            f"Roll={telemetry['pid_data']['roll']['error']:.3f}\n"
            f"Base Motor States: {base_motors}\n"
            f"Final Motor States: {final_motors}\n"
            f"ESC Pulse Values: {[t['pulse'] for t in telemetry['thrusters']]}\n"
            f"=============================\n"
        )
        
        logger.info(debug_info)
        
    def start_orientation_thread(self):
        """Start a thread to continuously update orientation data."""
        if not self.imu.available:
            logger.warning("IMU not available, orientation thread not started")
            return False
            
        self.orientation_running = True
        self.orientation_thread = threading.Thread(target=self._orientation_updater)
        self.orientation_thread.daemon = True
        self.orientation_thread.start()
        logger.info("Orientation update thread started")
        return True
        
    def _orientation_updater(self):
        """Thread function to update orientation data."""
        logger.info("Orientation updater thread running")
        while self.orientation_running:
            heading, roll, pitch = self.imu.get_orientation()
            
            with self.pid_lock:
                self.current_heading = heading
                self.current_roll = roll
                self.current_pitch = pitch
                
                # Initialize target heading if needed
                if self.pid_enabled and self.target_heading is None:
                    self.target_heading = heading
                    self.pid_system.set_targets(roll=0, pitch=0, yaw=heading)
                    logger.info(f"Target heading initialized to {heading:.1f} degrees")
                
                # Update the PID system with new sensor data
                if self.pid_enabled:
                    self.pid_system.process_sensor_data(roll, pitch, heading, self.current_depth)
            
            # Small sleep to prevent overwhelming the CPU
            time.sleep(0.01)
            
        logger.info("Orientation updater thread stopped")
    
    def initialize_thrusters(self):
        """Initialize all thruster ESCs."""
        logger.info("Initializing all thrusters...")
        self.pid_system.initialize()
        logger.info("All thrusters initialized")
    
    
    def process_command(self, command_data):
        """Process received command data."""
        command_processed = False
        
        if 'motor_values' in command_data:
            motor_values = command_data['motor_values']
            if isinstance(motor_values, list) and len(motor_values) == len(self.thrusters):
                # Check if values have changed significantly
                if any(abs(old - new) > 0.05 for old, new in zip(self.base_motor_states, motor_values)):
                    logger.info(f"New motor values received: {[f'{x:.2f}' for x in motor_values]}")
                    command_processed = True
                
                self.base_motor_states = motor_values
                
                # Extract joystick controls from motor values
                # This is a simplified mapping - actual mapping may need adjustment
                forward = (motor_values[2] + motor_values[3]) / 2  # Back motors forward
                strafe = (motor_values[1] - motor_values[0]) / 2   # Lateral difference
                vertical = (motor_values[4] + motor_values[5] + motor_values[6] + motor_values[7]) / 4  # Vertical average
                yaw = (motor_values[0] + motor_values[2] - motor_values[1] - motor_values[3]) / 4  # Rotational difference
                
                # Set movement in PID system
                self.pid_system.set_movement(forward, strafe, yaw, vertical)
                    
        if 'pid_enabled' in command_data:
            enable = bool(command_data['pid_enabled'])
            if enable != self.pid_enabled:
                self.set_pid_enabled(enable)
        
        if 'heading_pid_enabled' in command_data:
            enable = bool(command_data['heading_pid_enabled'])
            if enable != self.heading_pid_enabled:
                self.set_heading_pid_enabled(enable)       
                
        if 'pid_heading' in command_data:
            # Allow setting a specific target heading
            new_heading = float(command_data['pid_heading'])
            with self.pid_lock:
                self.target_heading = new_heading
                self.pid_system.set_targets(yaw=new_heading)
                logger.info(f"Target heading updated to {new_heading:.1f}")
        
        if 'pid_gains' in command_data:
            gains = command_data['pid_gains']
            if 'heading' in gains and len(gains['heading']) == 3:
                p, d, i = gains['heading']
                self.pid_system.pid_yaw = PID_Controller(p, d, i, 0.1)
                logger.info(f"Heading PID gains updated: P={p}, I={i}, D={d}")
                
            if 'pitch' in gains and len(gains['pitch']) == 3:
                p, d, i = gains['pitch']
                self.pid_system.pid_pitch = PID_Controller(p, d, i, 0.1)
                logger.info(f"Pitch PID gains updated: P={p}, I={i}, D={d}")
                
            if 'roll' in gains and len(gains['roll']) == 3:
                p, d, i = gains['roll']
                self.pid_system.pid_roll = PID_Controller(p, d, i, 0.1)
                logger.info(f"Roll PID gains updated: P={p}, I={i}, D={d}")
                
        return command_processed
                
    def set_pid_enabled(self, enabled):
        """Enable or disable PID stabilization."""
        if enabled and not self.imu.available:
            logger.warning("Cannot enable PID: IMU not available")
            return False
            
        with self.pid_lock:
            if enabled:
                # Reset PIDs and initialize with current orientation
                heading, roll, pitch = self.imu.get_orientation()
                self.target_heading = heading
                self.pid_system.set_targets(roll=0, pitch=0, yaw=heading)
                
            self.pid_enabled = enabled
            self.pid_system.enable_stabilization(enabled)
            logger.info(f"PID stabilization {'enabled' if enabled else 'disabled'}")
            return True
    
    def set_heading_pid_enabled(self, enabled):
        """Enable or disable just the heading PID control."""
        with self.pid_lock:
            self.heading_pid_enabled = enabled and self.pid_enabled
            self.pid_system.toggle_axis_stabilization('yaw', self.heading_pid_enabled)
            logger.info(f"Heading PID control {'enabled' if self.heading_pid_enabled else 'disabled'}")
    
    def update_thrusters(self):
        """Update thruster speeds based on current commands and PID adjustments."""
        # Process new sensor data in the PID system
        with self.pid_lock:
            if self.pid_enabled and self.imu.available:
                self.pid_system.process_sensor_data(
                    self.current_roll, 
                    self.current_pitch, 
                    self.current_heading, 
                    self.current_depth
                )
    
    def run(self):
        """Main ROV control loop."""
        try:
            # Initialize hardware
            self.initialize_thrusters()
            
            # Start orientation updates if IMU available
            if self.imu.available:
                self.start_orientation_thread()
                
            # Start network server via EthernetManager
            self.ethernet.start_control_server()
            self.running = True
            
            logger.info("ROV running. Waiting for client connection...")
            
            # Main control loop variables
            last_status_time = time.time()
            last_activity_check = time.time()
            last_debug_time = time.time()
            
            while self.running:
                current_time = time.time()
                
                # Update thruster values based on commands and PID
                self.update_thrusters()
                
                # Send telemetry data periodically (every 200ms)
                if current_time - last_status_time >= 0.2:
                    self._send_telemetry()
                    last_status_time = current_time
                
                # Log debug info periodically (every 2 seconds)
                if current_time - last_debug_time >= 2.0:
                    self.log_debug_info()
                    last_debug_time = current_time
                
                # Check thruster activity periodically (every 3 seconds)
                if current_time - last_activity_check >= 3.0:
                    self.monitor_thruster_activity()
                    last_activity_check = current_time
                    
                # Check for client timeout (5 seconds without commands)
                if self.ethernet.connected and (current_time - self.last_command_time > 5.0):
                    logger.warning("Client connection timed out (no commands received)")
                    # Connection will be handled by the EthernetManager
                    
                # Small sleep to prevent CPU hogging
                time.sleep(0.01)
                    
        except KeyboardInterrupt:
            logger.info("ROV operation interrupted by user")
        except Exception as e:
            logger.error(f"Error in ROV operation: {e}")
        finally:
            self.shutdown()
    
    def _send_telemetry(self):
        """Send telemetry data to the connected client."""
        if not self.ethernet.connected:
            return
            
        # Get PID system telemetry
        pid_telemetry = self.pid_system.get_telemetry()
        
        # Prepare telemetry data
        telemetry = {
            "timestamp": time.time(),
            "orientation": {
                "heading": self.current_heading,
                "roll": self.current_roll,
                "pitch": self.current_pitch
            },
            "target_heading": self.target_heading,
            "pid_enabled": self.pid_enabled,
            "heading_pid_enabled": pid_telemetry["axis_stabilization"]["yaw"],
            "calibration": self.imu.get_calibration_status() if self.imu.available else (0, 0, 0, 0),
            "thrusters": [t["speed"] for t in pid_telemetry["thrusters"]],
            "pid_output": {
                "heading": pid_telemetry["pid_data"]["yaw"]["p"] + pid_telemetry["pid_data"]["yaw"]["i"] + pid_telemetry["pid_data"]["yaw"]["d"],
                "pitch": pid_telemetry["pid_data"]["pitch"]["p"] + pid_telemetry["pid_data"]["pitch"]["i"] + pid_telemetry["pid_data"]["pitch"]["d"],
                "roll": pid_telemetry["pid_data"]["roll"]["p"] + pid_telemetry["pid_data"]["roll"]["i"] + pid_telemetry["pid_data"]["roll"]["d"]
            }
        }
        
        # Send telemetry via the ethernet manager
        self.ethernet._send_data(json.dumps(telemetry).encode('utf-8'))
            
    def monitor_thruster_activity(self):
        """Report on thruster activity in the last few seconds."""
        active_thrusters = []
        for thruster in self.thrusters:
            if abs(thruster.current_speed) > 0.01:  # If thruster is not at zero
                active_thrusters.append(f"{thruster.name}({thruster.current_speed:.2f})")
        
        if active_thrusters:
            logger.info(f"Active thrusters: {', '.join(active_thrusters)}")
        else:
            logger.info("All thrusters idle")

    def shutdown(self):
        """Safely shut down the ROV system."""
        logger.info("Shutting down ROV...")
        
        # Stop thrusters using PID system
        logger.info("Stopping all thrusters...")
        self.pid_system.shutdown()
        
        # Stop threads
        self.running = False
        self.orientation_running = False
        if self.orientation_thread and self.orientation_thread.is_alive():
            self.orientation_thread.join(timeout=1.0)
        
        # Close connections
        self.ethernet.shutdown()

        # Close hardware
        logger.info("Deinitializing PCA9685...")
        self.pca.deinit()
        
        if self.imu.available:
            logger.info("Closing IMU connection...")
            self.imu.close()
            
        logger.info("ROV shutdown complete")

# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description='ROV Control System with Arash PID Stabilization')
    parser.add_argument('--disable-pid', action='store_true', help='Disable PID stabilization')
    parser.add_argument('--disable-heading-pid', action='store_true', help='Disable only heading PID stabilization')
    parser.add_argument('--log-level', type=str, default='INFO',
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                      help='Logging level')
    args = parser.parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(args.log_level)
    
    # Create and run the ROV
    rov = ROV(pid_enabled=not args.disable_pid)
    
    # Apply heading-specific setting
    if args.disable_heading_pid:
        rov.heading_pid_enabled = False
        rov.pid_system.toggle_axis_stabilization('yaw', False)
        logger.info("Heading PID disabled via command-line option")
        
    try:
        rov.run()
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
    finally:
        rov.shutdown()
        logger.info("Program terminated")

if __name__ == '__main__':
    main()