import logging
import time
import threading
import argparse


from hardware.pca9685 import PCA9685, PCA9685Channel
from hardware.thruster import Thruster
from hardware.servo import Servo, Arm, ArmState
from hardware.imu import IMUSensor
from hardware.controller import ControllerMapper
from hardware.ethernet_man import EthernetManager
from hardware.pid_controller import ChassisControl

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

# --------------------------- Minimal ROV Class for Thruster Testing ---------------------------
class ROV:
    """Minimal ROV system for testing thruster functionality and Ethernet communication."""
    
    def __init__(self, stabilization_enabled=True):
        logger.info("Initializing ROV...")
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50
        
        #UNCOMMENT FOR IT TO WORK WITH TRUSTERS
        # Create thruster objects using a predefined channel map
        # self.thruster_channels = [13, 9, 10, 8, 11, 14, 12, 15]
        # self.thruster_names = [
        #     "FrontLeft", "FrontRight", "BackLeft", "BackRight",
        #     "FrontLeftUp", "FrontRightUp", "BackRightUp", "BackLeftUp"
        # ]
        # self.thrusters = []
        # for i, channel in enumerate(self.thruster_channels):
        #     name = self.thruster_names[i] if i < len(self.thruster_names) else f"Thruster{i}"
        #     self.thrusters.append(Thruster(channel, self.pca, name=name))

        # self.thrusters_initialized = False
        # self.b_button_press_time = 0

        self.thrusters = []
        # self.imu = 0

        self.controller_mapper = ControllerMapper()

        self.imu = IMUSensor()
        self.orientation_thread = None
        self.orientation_running = False
        self.current_heading = 0
        self.current_roll = 0
        self.current_pitch = 0

        self.left_x = 0.0
        self.left_y = 0.0
        self.right_x = 0.0
        self.right_y = 0.0
        self.left_trigger = 0.0
        self.right_trigger = 0.0

        # Create arm
        self.prev_button_states = {}
        self.arm = Arm(self.pca)

        self.chassis_control = ChassisControl()
        self.pid_lock = threading.Lock()  # For thread-safe PID updates
        self.stabilization_enabled = stabilization_enabled and self.imu.available
        
        # Initialize Ethernet Manager for network communication
        self.ethernet = EthernetManager(control_ip='192.168.1.237', control_port=4891)
        self.ethernet.set_control_callback(self.process_command)
        
        self.base_motor_states = [0.0] * 8
        self.pid_motor_adjustments = [0.0] * 8
        self.final_motor_states = [0.0] * 8
        self.last_command_time = time.time()
        self.running = False
        
        if self.stabilization_enabled:
            logger.info("PID stabilization is ENABLED")
        else:
            logger.info("PID stabilization is DISABLED")
        logger.info("Minimal ROV initialization complete")

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
        last_log_time = 0
        log_interval = 1.0  # Log IMU data every second
        
        while self.orientation_running:
            heading, roll, pitch = self.imu.get_orientation()
            
            with self.pid_lock:
                self.current_heading = heading
                self.current_roll = roll
                self.current_pitch = pitch
            
            # Log IMU data periodically
            current_time = time.time()
            if current_time - last_log_time > log_interval:
                # Get calibration status
                sys, gyro, accel, mag = self.imu.get_calibration_status()
                # logger.info(f"IMU Data - Heading: {heading:.2f}°, Roll: {roll:.2f}°, Pitch: {pitch:.2f}°")
                # logger.info(f"IMU Calibration - Sys: {sys}/3, Gyro: {gyro}/3, Accel: {accel}/3, Mag: {mag}/3")
                
                # Add IMU data to telemetry if a client is connected
                if self.ethernet.connected:
                    telemetry = {
                        "imu": {
                            "heading": heading,
                            "roll": roll,
                            "pitch": pitch,
                            "calibration": {
                                "sys": sys,
                                "gyro": gyro,
                                "accel": accel,
                                "mag": mag
                            }
                        }
                    }
                    self.ethernet.send_telemetry(telemetry)
                    
                last_log_time = current_time
            
            # Small sleep to prevent overwhelming the CPU
            time.sleep(0.01)
        logger.info("Orientation updater thread stopped")
    
    def initialize_thrusters(self):
        """Initialize all thrusters."""
        if self.thrusters_initialized:
            logger.info("Thrusters already initialized")
            return
            
        logger.info("Initializing all thrusters...")
        if self.thrusters:
            for thruster in self.thrusters:
                thruster.initialize()
            self.thrusters_initialized = True
            logger.info("All thrusters initialized successfully")

    def start(self) -> None:
        """Start the ROV system."""
        logger.info("Starting ROV system...")
        
        # # Initialize thrusters if any
        # if self.thrusters:
        #     for thruster in self.thrusters:
        #         thruster.initialize()

        if self.imu.available:
            self.start_orientation_thread()
        self.ethernet.start_control_server()
        self.running = True
        self._main_loop()
    
    def _main_loop(self) -> None:
        """Main control loop for the ROV."""
        logger.info("Entering main loop...")
        
        while self.running:
            try:
                current_time = time.time()
                
                # Update motor states based on PID and arm mode
                self.update_motor_states()
    
                # Check for timeout (lost connection)
                if current_time - self.last_command_time > 5.0:
                    # Stop all motors if no commands received for 5 seconds
                    for thruster in self.thrusters:
                        thruster.set_speed(0.0)
                
                time.sleep(0.01)  # Small delay for loop iteration
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(0.5)
    
    def update_motor_states(self):
        """Update motor states based on control mode and PID."""

        imu_data = [
            0, 0, 0,  # X, Y, Z position defaults
            self.current_roll,
            self.current_pitch,
            self.current_heading
        ]
        
        # Apply PID adjustments if stabilization is enabled
        if self.stabilization_enabled and self.imu.available:
            with self.pid_lock:
                # Get current IMU data
                imu_data = [
                0, 0, 0,  # X, Y, Z position (not available from IMU, would need additional sensors)
                self.current_roll,
                self.current_pitch,
                self.current_heading
                ]
                
                # Log detailed IMU data for PID calculations
                logger.debug(f"PID Targets - Roll: 0.00°, Pitch: 0.00°, Yaw: {self.chassis_control.yaw_target:.2f}°")
                logger.debug(f"PID Current - Roll: {imu_data[3]:.2f}°, Pitch: {imu_data[4]:.2f}°, Heading: {imu_data[5]:.2f}°")
                
                # Calculate PID corrections - each individual PID controller will now log its details
                pid_corrections = self.chassis_control.PIDcorrection(imu_data)
                
                # Log final corrections after all PID calculations
                # logger.debug(f"PID Corrections Combined: [{', '.join([f'{x:.4f}' for x in pid_corrections])}]")
                
                controller = self.chassis_control.controllerInput(self.left_x, self.left_y, self.right_x, self.right_y, 
                                                                self.left_trigger, self.right_trigger)
                # logger.debug(f"Controller Input: [{', '.join([f'{x:.2f}' for x in controller])}]")

                vectorret = self.chassis_control.addVectors(controller, pid_corrections)
                # logger.debug(f"Combined Vector: [{', '.join([f'{x:.2f}' for x in vectorret])}]")

                # Convert PID corrections to motor adjustments
                self.final_motor_states = self.chassis_control.arcadeDrive6(vectorret)
                # logger.debug(f"Final Motor Values: [{', '.join([f'{x:.2f}' for x in self.final_motor_states])}]")
                
                # Normalize if any value exceeds limits
                max_val = max(abs(val) for val in self.final_motor_states)
                if max_val > 1.0:
                    self.final_motor_states = [val/max_val for val in self.final_motor_states]
        else:

            controller = self.chassis_control.controllerInput(self.left_x, self.left_y, self.right_x, self.right_y, 
                                                                  self.left_trigger, self.right_trigger)
            # Use base motor states without PID
            self.final_motor_states = self.chassis_control.arcadeDrive6(controller)

        max_val = max(abs(val) for val in self.final_motor_states)
        if max_val > 1.0:
            self.final_motor_states = [val/max_val for val in self.final_motor_states]
        # Apply motor states to thrusters
        if self.thrusters:
            for i, thruster in enumerate(self.thrusters):
                if i < len(self.final_motor_states):
                    thruster.set_speed(self.final_motor_states[i])
                
        self.chassis_control.updateTarget(
                        imu_data, self.left_x, self.left_y, self.right_x, self.right_y,
                        self.right_trigger, self.left_trigger
                    )
    def get_controller_mapping(self):
        """Return the current controller mapping for telemetry or UI"""
        return self.controller_mapper.get_current_mapping()
    

    def process_command(self, command_data):
        """Process received command data."""
        command_processed = False
        
        # Handle controller mapping commands
        if 'remap' in command_data:
            remap_data = command_data['remap']
            source = remap_data.get('source')
            target = remap_data.get('target')
            
            if source and target:
                self.controller_mapper.set_mapping(source, target)
                self.controller_mapper.save_mapping()
                command_processed = True
                return command_processed
            elif 'reset' in remap_data and remap_data['reset']:
                self.controller_mapper.reset_mapping()
                self.controller_mapper.save_mapping()
                command_processed = True
                return command_processed
        
        # Handle the controller data format
        if 'controller' in command_data:
            # Apply mapping to the controller data
            original_controller = command_data['controller']
            controller = self.controller_mapper.apply_mapping(original_controller)
            
            # Extract and store controller values
            self.left_x = controller.get('left_stick_x', 0.0)
            self.left_y = controller.get('left_stick_y', 0.0)
            self.right_x = controller.get('right_stick_x', 0.0)
            self.right_y = controller.get('right_stick_y', 0.0)
            self.left_trigger = controller.get('left_trigger', 0.0)
            self.right_trigger = controller.get('right_trigger', 0.0)
            
            # Apply deadzone
            def apply_deadzone(value, deadzone=0.05):
                return 0.0 if abs(value) < deadzone else value
                
            self.left_x = apply_deadzone(self.left_x)
            self.left_y = apply_deadzone(self.left_y)
            self.right_x = apply_deadzone(self.right_x)
            self.right_y = apply_deadzone(self.right_y)
            
            # Update PID targets if stabilization is enabled
            if self.stabilization_enabled and self.imu.available:
                with self.pid_lock:
                    imu_data = [0, 0, 0, self.current_roll, self.current_pitch, self.current_heading]
                    self.chassis_control.updateTarget(
                        imu_data, self.left_x, self.left_y, self.right_x, self.right_y,
                        self.right_trigger, self.left_trigger
                    )
            else:
                # Calculate motor values without PID
                controller_input = self.chassis_control.controllerInput(
                    self.left_x, self.left_y, self.right_x, self.right_y,
                    self.right_trigger, self.left_trigger
                )
                self.base_motor_states = self.chassis_control.arcadeDrive6(controller_input)

            # Save the current state before processing any new commands
            previous_state = self.arm.current_state
        
            # Get button states - these are now using the mapped controller data
            # Get button states - these are now using the mapped controller data
            a_button = controller.get('a', 0)
            b_button = controller.get('b', 0)
            x_button = controller.get('x', 0)
            y_button = controller.get('y', 0)
            lb_button = controller.get('lb', 0)
            rb_button = controller.get('rb', 0)
                        
            # Get previous button states
            prev_a = self.prev_button_states.get('a', 0)
            prev_b = self.prev_button_states.get('b', 0)
            prev_x = self.prev_button_states.get('x', 0)
            prev_y = self.prev_button_states.get('y', 0)
            prev_lb = self.prev_button_states.get('lb', 0)
            prev_rb = self.prev_button_states.get('rb', 0)

            # ADD THIS CODE BLOCK HERE - More complete handling for remapped buttons
            # Check if any button is mapped to trigger another button's function
            for source, target in self.controller_mapper.mapping.items():
                # Check if the source is in the original controller data AND is pressed
                if source in original_controller:
                    # If this source input is active in the original controller
                    if original_controller[source] == 1:
                        # Update the mapped button state accordingly
                        if target == 'a': a_button = 1
                        elif target == 'b': b_button = 1
                        elif target == 'x': x_button = 1
                        elif target == 'y': y_button = 1
                        elif target == 'lb': lb_button = 1
                        elif target == 'rb': rb_button = 1
                    
                    # Also handle previous button states for edge detection
                    if source in self.prev_button_states and self.prev_button_states.get(source, 0) == 1:
                        # Update the previous mapped button state accordingly
                        if target == 'a': prev_a = 1
                        elif target == 'b': prev_b = 1
                        elif target == 'x': prev_x = 1
                        elif target == 'y': prev_y = 1
                        elif target == 'lb': prev_lb = 1
                        elif target == 'rb': prev_rb = 1
            
            # Process button inputs for arm control - each check is independent
            if a_button == 1:
                self.arm.open_claw()
                command_processed = True
            # B button now used exclusively for thruster initialization
            if b_button == 1:
                current_time = time.time()
                
                # First press, record time
                if prev_b == 0:
                    self.b_button_press_time = current_time
                    logger.info("B button pressed - hold for 3 seconds to initialize thrusters")
                
                # Check if button has been held for 3+ seconds
                if not self.thrusters_initialized and (current_time - self.b_button_press_time >= 3.0):
                    logger.info("B button held for 3 seconds, initializing thrusters...")
                    self.initialize_thrusters()
                    # Reset timer to prevent repeated initialization
                    self.b_button_press_time = current_time + 100  # Set far in the future
                    command_processed = True

            # For state-changing buttons, only react on press (not hold)
            # and only if not already in that state
            # For state-changing buttons, now using if instead of elif
            # and removing the state check which causes issues with remapping
            if x_button == 1 and prev_x == 0:  # Removed state check
                self.arm.set_state(ArmState.STOWED)
                command_processed = True
            if y_button == 1 and prev_y == 0:  # Removed state check
                self.arm.set_state(ArmState.FULLY_OUT)
                command_processed = True
            if lb_button == 1 and prev_lb == 0:  # Removed state check
                self.arm.set_state(ArmState.OUT_DOWN)
                command_processed = True
            if rb_button == 1 and prev_rb == 0:  # Removed state check
                self.arm.set_state(ArmState.FULLY_DOWN)
                command_processed = True

            # Process D-pad (hat) inputs for wrist rotation and claw - CHANGED FROM elif to if
            dpad_x = controller.get('dpad_x', 0)
            dpad_y = controller.get('dpad_y', 0)
            prev_dpad_y = self.prev_button_states.get('dpad_y', 0)
            if dpad_x == -1:  # Left on D-pad
                self.arm.adjust_wrist(-1)
                command_processed = True
            if dpad_x == 1:  # Right on D-pad
                self.arm.adjust_wrist(1)
                command_processed = True


            if dpad_y == -1:  # Down on D-pad - close claw while held
                self.arm.adjust_claw(-1, step=0.2)
                command_processed = True
            elif dpad_y == 1:  # Up on D-pad - open claw while held
                self.arm.adjust_claw(1, step=0.3)
                command_processed = True

            # Stop claw when D-pad released from up/down
            if dpad_y == 0 and (prev_dpad_y == 1 or prev_dpad_y == -1):
                self.arm.stop_claw()  # Stop the claw when D-pad y-axis is released
                command_processed = True
            
            # Update previous button states
            self.prev_button_states = {
                'a': a_button,
                'b': b_button,
                'x': x_button,
                'y': y_button,
                'lb': lb_button,
                'rb': rb_button,
                'dpad_y': dpad_y
            }
        
        # Handle motor_values if present
        if 'motor_values' in command_data and self.thrusters:
            motor_values = command_data['motor_values']
            if isinstance(motor_values, list) and len(motor_values) == len(self.thrusters):
                # Check if values have changed significantly
                if any(abs(old - new) > 0.05 for old, new in zip(self.base_motor_states, motor_values)):
                    logger.info(f"New motor values received: {[f'{x:.2f}' for x in motor_values]}")
                    command_processed = True
                
                self.base_motor_states = motor_values
                
        # Update the last command time
        self.last_command_time = time.time()
        
        return command_processed
    
    def shutdown(self) -> None:
        """Shutdown the ROV system."""
        logger.info("Shutting down ROV system...")
        self.running = False
        
        # Stop thrusters if any
        if self.thrusters:
            for thruster in self.thrusters:
                thruster.stop()

        # Move the arm to a safe position
        try:
            self.arm.set_state(ArmState.FULLY_OUT)
            time.sleep(1)  # Wait for arm to reach position
        except Exception as e:
            logger.error(f"Error stowing arm during shutdown: {e}")

        # Clean up other resources
        if self.orientation_thread and self.orientation_thread.is_alive():
            self.orientation_thread.join(timeout=1.0)

        if self.imu.available:
            self.imu.close()

        self.ethernet.shutdown()
        self.pca.deinit()
        logger.info("ROV system shutdown complete")

# --------------------------- Main Entry Point ---------------------------
# Keep only this main function
def main():
    parser = argparse.ArgumentParser(description='ROV Control System with Arm and PID Stabilization')
    parser.add_argument('--disable-stabilization', action='store_true', help='Disable PID stabilization')
    parser.add_argument('--log-level', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')
    args = parser.parse_args()
    logging.getLogger().setLevel(args.log_level)
    
    rov = ROV(stabilization_enabled=not args.disable_stabilization)
    try:
        rov.start()
    except KeyboardInterrupt:
        logger.info("ROV interrupted by user")
    except Exception as e:
        logger.error(f"Error in ROV system: {e}")
    finally:
        rov.shutdown()

if __name__ == '__main__':
    main()