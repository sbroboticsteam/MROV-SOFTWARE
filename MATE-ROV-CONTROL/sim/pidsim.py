import pygame
from pygame.locals import *
import numpy as np
import math
import time
import sys
import os
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from datetime import datetime
import threading
import queue
import logging

# Constants
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
BG_COLOR = (20, 20, 30)
TEXT_COLOR = (240, 240, 240)
GRID_COLOR = (40, 40, 60)
PLOT_BG_COLOR = (30, 30, 40)

# ROV dimensions
ROV_WIDTH = 150
ROV_HEIGHT = 80
ROV_DEPTH = 150

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PIDSimulator_BNO055")

# Add BNO055 sensor path to system path
# Assuming bno055.py is in ../imuTesting relative to this script's directory (sim)
script_dir = os.path.dirname(os.path.abspath(__file__))
imu_testing_dir = os.path.join(os.path.dirname(script_dir), 'imuTesting')
sys.path.insert(0, imu_testing_dir)

# Try to import BNO055 module
try:
    from bno055 import BNO055, BNO055_ADDRESS_A
    bno055_available = True
    logger.info("BNO055 sensor module successfully imported")
except ImportError as e:
    logger.warning(f"BNO055 module not found in {imu_testing_dir}: {e}. Hardware mode will not be available.")
    bno055_available = False
except Exception as e:
    logger.error(f"An unexpected error occurred importing BNO055: {e}")
    bno055_available = False

# --- PID Controller Classes (Copied from original) ---
class ElapsedTime:
    def __init__(self):
        self.reset()

    def reset(self):
        self._start_time = time.time()

    def seconds(self):
        return time.time() - self._start_time

class PID_Controller:
    def __init__(self, *args):
        self.runtime = ElapsedTime()
        self.tolerance = 0.0
        self.area = 0.0

        self.kp = 0.0
        self.kd = 0.0
        self.ki = 0.0
        self.a = 0.0 # Filter coefficient (0=no filter, 1=max filter)

        self.P = 0.0
        self.I = 0.0
        self.D = 0.0

        self.delta_time = 0.0
        self.previous_error = 0.0
        self.previous_target = 0.0
        self.previous_filter_estimate = 0.0
        self.current_filter_estimate = 0.0
        self.error_change = 0.0
        self.error = 0.0

        # Constructor overloads
        if len(args) == 1:
            self.kp = args[0]
        elif len(args) == 2:
            self.kp = args[0]
            self.kd = args[1]
        elif len(args) == 3:
            self.kp = args[0]
            self.kd = args[1]
            self.ki = args[2]
        elif len(args) == 4:
            self.kp = args[0]
            self.kd = args[1]
            self.ki = args[2]
            self.a = args[3]

    def PID_Power(self, curr_pos, target_pos):
        self.error = target_pos - curr_pos
        self.error_change = self.error - self.previous_error

        self.P = self.kp * self.error

        self.delta_time = self.runtime.seconds()
        self.runtime.reset()

        # Prevent division by zero or excessively small dt
        if self.delta_time < 0.001:
            self.delta_time = 0.001

        # Integral term calculation
        self.area += ((self.error + self.previous_error) * self.delta_time) / 2

        # Integral windup prevention
        if abs(self.error) < self.tolerance:
            self.area = 0.0
        if target_pos != self.previous_target: # Reset integral if target changes
            self.area = 0.0

        self.I = self.area * self.ki

        # Derivative term calculation with simple low-pass filter
        self.current_filter_estimate = ((1 - self.a) * self.error_change +
                                        self.a * self.previous_filter_estimate)

        self.D = self.kd * (self.current_filter_estimate / self.delta_time)

        # Update previous values
        self.previous_error = self.error
        self.previous_filter_estimate = self.current_filter_estimate
        self.previous_target = target_pos

        return self.P + self.I + self.D

# --- BNO055 Data Provider ---
class BNO055DataProvider:
    """Provides IMU sensor data using BNO055 for the PID simulator"""

    def __init__(self, mode="simulated", bus_number=7, address=BNO055_ADDRESS_A):
        """
        Initialize the BNO055 data provider

        Args:
            mode: "hardware" for real BNO055, "simulated" for simulated data
            bus_number: I2C bus number (for hardware mode)
            address: I2C address of the BNO055 sensor
        """
        self.mode = mode
        self.bus_number = bus_number
        self.address = address
        self.bno_sensor = None
        self.running = False
        self.data_queue = queue.Queue(maxsize=100)
        self.thread = None

        # Data history
        self.history = {
            'roll': [],
            'pitch': [],
            'yaw': [],
            'depth': [], # Depth will always be simulated
            'timestamp': []
        }

        # Current sensor values
        self.current_data = {
            'roll': 0.0,
            'pitch': 0.0,
            'yaw': 0.0,
            'depth': 0.0, # Start depth at 0
            'timestamp': time.time()
        }

        # Initialize the sensor if hardware mode
        if self.mode == "hardware" and bno055_available:
            self._initialize_hardware()
        elif self.mode == "hardware" and not bno055_available:
            logger.warning("Hardware mode requested but BNO055 module not available. Falling back to simulated mode.")
            self.mode = "simulated"

    def _initialize_hardware(self):
        """Initialize connection to BNO055 hardware"""
        try:
            # Initialize BNO055 sensor
            self.bno_sensor = BNO055(bus_number=self.bus_number, address=self.address)
            if not self.bno_sensor.begin():
                raise RuntimeError("Failed to initialize BNO055 sensor.")

            logger.info(f"BNO055 sensor initialized on bus {self.bus_number}, address {self.address:#04x}")
            self.mode = "hardware"
        except Exception as e:
            logger.error(f"Error initializing BNO055 hardware: {e}")
            logger.info("Falling back to simulated data mode")
            self.mode = "simulated"
            if self.bno_sensor:
                self.bno_sensor.close()
            self.bno_sensor = None

    def start(self):
        """Start the data collection thread"""
        if self.thread and self.thread.is_alive():
            logger.info("Data provider already running")
            return

        self.running = True

        if self.mode == "hardware" and self.bno_sensor:
            self.thread = threading.Thread(target=self._hardware_reader_thread, daemon=True)
        else:
            # Ensure mode is simulated if hardware failed or wasn't requested
            self.mode = "simulated"
            self.thread = threading.Thread(target=self._simulated_data_thread, daemon=True)

        self.thread.start()
        logger.info(f"Started BNO055 data provider in {self.mode} mode")

    def _hardware_reader_thread(self):
        """Thread to read data from BNO055 sensor"""
        if not self.bno_sensor:
            logger.error("BNO055 Sensor not initialized for hardware reading")
            self.running = False
            return

        # Sample at ~20Hz
        delay = 0.05
        simulated_depth = self.current_data['depth'] # Start with current depth

        while self.running:
            try:
                # Read orientation data from BNO055
                # Note: BNO055 Euler angles: Heading (Yaw), Roll, Pitch
                heading, roll, pitch = self.bno_sensor.get_euler()

                # Simulate depth changes (BNO055 doesn't measure depth)
                # Add small random walk to simulated depth
                simulated_depth += np.random.normal(0, 0.01)
                simulated_depth = max(0, simulated_depth) # Depth cannot be negative

                # Create data packet
                data = {
                    'roll': roll,
                    'pitch': pitch,
                    'yaw': heading, # Use BNO055 heading as yaw
                    'depth': simulated_depth, # Use simulated depth
                    'timestamp': time.time()
                }

                # Update current data
                self.current_data = data

                # Store in history
                for key in ['roll', 'pitch', 'yaw', 'depth', 'timestamp']:
                    self.history[key].append(data[key])

                # Trim history to reasonable size
                max_history = 1000
                if len(self.history['timestamp']) > max_history:
                    for key in self.history:
                        self.history[key] = self.history[key][-max_history:]

                # Put into queue for other components
                try:
                    self.data_queue.put(data, block=False)
                except queue.Full:
                    pass # Skip this point if queue is full

                # Wait for next sample time
                time.sleep(delay)

            except IOError as e:
                logger.error(f"I/O error reading from BNO055: {e}. Check connection.")
                time.sleep(1.0) # Wait longer on I/O error
            except Exception as e:
                logger.error(f"Unexpected error reading from BNO055: {e}")
                time.sleep(1.0)

    def _simulated_data_thread(self):
        """Thread to generate simulated IMU data (including depth)"""
        # Sample at ~20Hz
        delay = 0.05

        # Create simulated data with realistic noise and drift
        t = 0.0
        roll_drift = 0.0
        pitch_drift = 0.0
        yaw_drift = 0.0
        depth = 1.0 # Start depth at 1m

        while self.running:
            # Add some noise and drift to values
            roll_noise = np.random.normal(0, 0.2)
            pitch_noise = np.random.normal(0, 0.2)
            yaw_noise = np.random.normal(0, 0.5)
            depth_noise = np.random.normal(0, 0.05)

            # Slowly drift over time
            roll_drift += np.random.normal(0, 0.01)
            pitch_drift += np.random.normal(0, 0.01)
            yaw_drift += np.random.normal(0, 0.05)
            depth += np.random.normal(0, 0.01) # Depth also drifts slightly

            # Limit drift to realistic values
            roll_drift = max(-2.0, min(2.0, roll_drift))
            pitch_drift = max(-2.0, min(2.0, pitch_drift))
            yaw_drift = max(-5.0, min(5.0, yaw_drift))
            depth = max(0.0, min(10.0, depth)) # Limit depth between 0 and 10m

            # Create data object
            data = {
                'roll': roll_noise + roll_drift,
                'pitch': pitch_noise + pitch_drift,
                'yaw': (yaw_noise + yaw_drift) % 360.0,  # Normalize yaw to 0-360 range
                'depth': depth + depth_noise,
                'timestamp': time.time()
            }

            # Update current data
            self.current_data = data

            # Store in history
            for key in ['roll', 'pitch', 'yaw', 'depth', 'timestamp']:
                self.history[key].append(data[key])

            # Trim history to reasonable size
            max_history = 1000
            if len(self.history['timestamp']) > max_history:
                for key in self.history:
                    self.history[key] = self.history[key][-max_history:]

            # Put into queue for other components
            try:
                self.data_queue.put(data, block=False)
            except queue.Full:
                pass # Skip this point if queue is full

            t += delay
            time.sleep(delay)

    def get_latest_data(self):
        """Get the latest sensor data"""
        # Get all available data from the queue to ensure freshness
        while not self.data_queue.empty():
            try:
                data = self.data_queue.get(block=False)
                self.current_data = data
            except queue.Empty:
                break # Queue is empty, use the last data read

        return self.current_data

    def stop(self):
        """Stop the data collection thread and close sensor"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            if self.thread.is_alive():
                logger.warning("Data provider thread did not terminate cleanly.")
            self.thread = None

        # Close hardware connections if needed
        if self.mode == "hardware" and self.bno_sensor:
            try:
                self.bno_sensor.close()
                logger.info("BNO055 sensor connection closed.")
            except Exception as e:
                logger.error(f"Error closing BNO055 sensor: {e}")
            self.bno_sensor = None

    def record_session(self, file_path=None, duration=60):
        """
        Record IMU data (Roll, Pitch, Yaw from BNO055/Sim, Simulated Depth) to a CSV file

        Args:
            file_path: Path to save the file (generated if None)
            duration: Recording duration in seconds
        """
        if not file_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = f"bno055_recording_{timestamp}.csv"

        logger.info(f"Recording BNO055 data to {file_path} for {duration} seconds")

        # Make sure data collection is running
        was_running = self.running
        if not was_running:
            self.start()
            time.sleep(0.5) # Give thread time to start

        if not self.running:
             logger.error("Failed to start data provider for recording.")
             return None

        # Collect data for the specified duration
        start_time = time.time()
        recorded_data = []

        while time.time() - start_time < duration:
            data = self.get_latest_data()
            recorded_data.append(data.copy())
            time.sleep(0.05)  # ~20Hz sampling

        # Stop if we started specifically for recording
        if not was_running:
            self.stop()

        # Write data to CSV
        try:
            with open(file_path, 'w', newline='') as f:
                import csv
                writer = csv.writer(f)
                # Write header
                writer.writerow(["timestamp", "roll", "pitch", "yaw", "depth"])

                # Write data rows
                for data in recorded_data:
                    writer.writerow([
                        data.get('timestamp', 0.0),
                        data.get('roll', 0.0),
                        data.get('pitch', 0.0),
                        data.get('yaw', 0.0),
                        data.get('depth', 0.0) # Depth is always simulated
                    ])

            logger.info(f"Recorded {len(recorded_data)} samples to {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Error writing data to file {file_path}: {e}")
            return None

# --- arcadeDrive6 Function (Copied from original) ---
def arcadeDrive6(input_vector):
    """
    Converts a 6 DOF input vector into thruster values

    Args:
        input_vector: [x, y, z, roll, pitch, yaw]

    Returns:
        8 thruster values: [planar_FL, planar_FR, planar_BR, planar_BL,
                           vertical_FL, vertical_FR, vertical_BL, vertical_BR]
    """
    # Input vector mapping:
    # input_vector[0]: Forward/Backward (X) - Not used directly by PID in this sim
    # input_vector[1]: Strafe Left/Right (Y) - Not used directly by PID in this sim
    # input_vector[2]: Up/Down (Z) - Controlled by Depth PID
    # input_vector[3]: Roll Correction - Controlled by Roll PID
    # input_vector[4]: Pitch Correction - Controlled by Pitch PID
    # input_vector[5]: Yaw Correction - Controlled by Yaw PID

    # Inverse Kinematics for Planar Thrusters (Yaw correction)
    # Assuming planar thrusters are angled for X, Y, and Yaw control
    # Simplified: Only use Yaw component for planar thrusters in PID correction
    yaw_power = input_vector[5]
    planar_front_left = -yaw_power
    planar_front_right = +yaw_power
    planar_back_right = -yaw_power
    planar_back_left = +yaw_power

    # Inverse Kinematics for Vertical Thrusters (Depth, Roll, Pitch Corrections)
    depth_power = input_vector[2]
    roll_power = input_vector[3]
    pitch_power = input_vector[4]

    vertical_front_left = -depth_power - roll_power - pitch_power
    vertical_front_right = -depth_power + roll_power - pitch_power
    vertical_back_left = -depth_power - roll_power + pitch_power
    vertical_back_right = -depth_power + roll_power + pitch_power

    # Scaling and Normalization
    def normalize_thrusters(thrusters):
        max_val = max(abs(t) for t in thrusters) if thrusters else 0
        if max_val > 1.0:
            thrusters = [t / max_val for t in thrusters]
        # Clamp values between -1 and 1 after normalization (or if max_val <= 1)
        thrusters = [max(-1.0, min(1.0, t)) for t in thrusters]
        return thrusters

    # Normalize Planar and Vertical Thruster Values Separately
    planar_thrusters = normalize_thrusters([planar_front_left, planar_front_right, planar_back_right, planar_back_left])
    vertical_thrusters = normalize_thrusters([vertical_front_left, vertical_front_right, vertical_back_left, vertical_back_right])

    # Return motor power values for all thrusters
    return planar_thrusters + vertical_thrusters

# --- ROVPhysics Class (Copied from original, minor adjustments) ---
class ROVPhysics:
    """ROV physics model for simulator"""

    def __init__(self):
        # Position and orientation
        self.position = np.array([0.0, 0.0, 0.0])  # x, y, z position (y is depth, negative is down)
        self.orientation = np.array([0.0, 0.0, 0.0])  # roll, pitch, yaw in degrees

        # Motion parameters
        self.velocity = np.array([0.0, 0.0, 0.0]) # x, y, z velocity
        self.angular_velocity = np.array([0.0, 0.0, 0.0]) # roll, pitch, yaw rates in rad/s

        # Physical properties
        self.mass = 10.0  # kg
        # Simplified moment of inertia (adjust if needed)
        self.moment_of_inertia = np.array([0.5, 1.0, 0.5])  # kg*m^2 (Roll, Pitch, Yaw) - Pitch often higher inertia
        self.drag_coefficient = 0.8 # Linear drag coefficient
        self.angular_drag = 1.5 # Angular drag coefficient

        # Thruster forces
        self.thruster_forces = np.zeros(8)
        self.max_thruster_force = 15.0 # Newtons per thruster at full power (1.0)

        # Buoyancy and Gravity
        self.gravity_force = 9.81 * self.mass
        # Assume slightly positive buoyancy when submerged
        # Volume displaced = mass / density_rov -> Buoyancy = Volume * density_water * g
        # Let's make it simpler: target a net buoyancy force
        self.net_buoyancy = 1.0 # Newtons (positive = tends to float up)
        # Assume center of buoyancy is slightly above center of mass for stability
        self.center_of_buoyancy_offset = np.array([0.0, 0.05, 0.0]) # Offset from CoM (x, y, z) in body frame

        # Environment
        self.water_depth = 0.0 # Current depth (positive value)

    def update_thruster_forces(self, motor_values):
        """Update thruster forces based on motor values (-1 to 1)"""
        # Ensure motor_values is a numpy array
        motor_values = np.array(motor_values)
        # Clamp values just in case
        motor_values = np.clip(motor_values, -1.0, 1.0)
        self.thruster_forces = motor_values * self.max_thruster_force

    def _body_to_world(self, vector):
        """Rotates a vector from body frame to world frame"""
        roll_rad = math.radians(self.orientation[0])
        pitch_rad = math.radians(self.orientation[1])
        yaw_rad = math.radians(self.orientation[2])

        c_r, s_r = math.cos(roll_rad), math.sin(roll_rad)
        c_p, s_p = math.cos(pitch_rad), math.sin(pitch_rad)
        c_y, s_y = math.cos(yaw_rad), math.sin(yaw_rad)

        # ZYX rotation matrix (Body to World)
        rot_matrix = np.array([
            [c_y*c_p, c_y*s_p*s_r - s_y*c_r, c_y*s_p*c_r + s_y*s_r],
            [s_y*c_p, s_y*s_p*s_r + c_y*c_r, s_y*s_p*c_r - c_y*s_r],
            [-s_p,    c_p*s_r,             c_p*c_r]
        ])
        return rot_matrix @ vector

    def update(self, dt):
        """Update ROV physics for one time step"""
        if dt <= 0: return # Avoid issues with zero or negative dt

        # --- Forces ---
        # Gravity (acting downwards in world frame)
        force_gravity_world = np.array([0.0, -self.gravity_force, 0.0])

        # Buoyancy (acting upwards relative to gravity, but applied at CoB)
        # Net buoyancy force (gravity - buoyancy) acts vertically
        force_buoyancy_world = np.array([0.0, self.net_buoyancy, 0.0])

        # Thruster forces (defined in body frame, need conversion)
        # Simplified thruster model: Assume forces act directly along axes
        # Planar thrusters (FL, FR, BR, BL) affect X, Y, Yaw
        # Vertical thrusters (VFL, VFR, VBL, VBR) affect Z, Roll, Pitch
        force_thrusters_body = np.zeros(3)
        torque_thrusters_body = np.zeros(3)

        # Thruster positions relative to CoM (example, adjust based on actual ROV)
        # Format: [x, y, z] where +x=forward, +y=up, +z=right
        pos_p_fl = np.array([-ROV_WIDTH*0.4, 0.0, -ROV_DEPTH*0.4])
        pos_p_fr = np.array([-ROV_WIDTH*0.4, 0.0, +ROV_DEPTH*0.4])
        pos_p_br = np.array([+ROV_WIDTH*0.4, 0.0, +ROV_DEPTH*0.4])
        pos_p_bl = np.array([+ROV_WIDTH*0.4, 0.0, -ROV_DEPTH*0.4])
        pos_v_fl = np.array([-ROV_WIDTH*0.4, -ROV_HEIGHT*0.3, -ROV_DEPTH*0.4])
        pos_v_fr = np.array([-ROV_WIDTH*0.4, -ROV_HEIGHT*0.3, +ROV_DEPTH*0.4])
        pos_v_bl = np.array([+ROV_WIDTH*0.4, -ROV_HEIGHT*0.3, -ROV_DEPTH*0.4])
        pos_v_br = np.array([+ROV_WIDTH*0.4, -ROV_HEIGHT*0.3, +ROV_DEPTH*0.4])

        # Thruster directions (unit vectors in body frame)
        # Planar thrusters angled at 45 degrees
        dir_p_fl = np.array([1, 0, -1]) / np.sqrt(2)
        dir_p_fr = np.array([1, 0, 1]) / np.sqrt(2)
        dir_p_br = np.array([-1, 0, 1]) / np.sqrt(2)
        dir_p_bl = np.array([-1, 0, -1]) / np.sqrt(2)
        # Vertical thrusters pointing straight up/down
        dir_v = np.array([0, 1, 0])

        thruster_configs = [
            (self.thruster_forces[0], pos_p_fl, dir_p_fl), # Planar FL
            (self.thruster_forces[1], pos_p_fr, dir_p_fr), # Planar FR
            (self.thruster_forces[2], pos_p_br, dir_p_br), # Planar BR
            (self.thruster_forces[3], pos_p_bl, dir_p_bl), # Planar BL
            (self.thruster_forces[4], pos_v_fl, dir_v),    # Vertical FL
            (self.thruster_forces[5], pos_v_fr, dir_v),    # Vertical FR
            (self.thruster_forces[6], pos_v_bl, dir_v),    # Vertical BL
            (self.thruster_forces[7], pos_v_br, dir_v),    # Vertical BR
        ]

        for force_magnitude, position, direction in thruster_configs:
            force_vector = direction * force_magnitude
            force_thrusters_body += force_vector
            torque_thrusters_body += np.cross(position, force_vector)

        # Convert thruster force from body to world frame
        force_thrusters_world = self._body_to_world(force_thrusters_body)

        # Drag forces (opposite to velocity, in world frame)
        # Simple linear drag model: F_drag = -C_d * V
        force_drag_world = -self.drag_coefficient * self.velocity

        # Total force in world frame
        net_force_world = force_gravity_world + force_buoyancy_world + force_thrusters_world + force_drag_world

        # --- Torques ---
        # Thruster torque (already calculated in body frame)
        torque_thrusters = torque_thrusters_body

        # Buoyancy torque (Restoring force due to CoB offset)
        # Force causing torque is the buoyant force, lever arm is CoB offset rotated to world frame
        # Simplified: Apply restoring torque based on roll/pitch in body frame
        # This torque tries to bring the ROV level
        restoring_torque_factor = 5.0 # Adjust for stability strength
        torque_buoyancy_body = np.array([
            -restoring_torque_factor * math.sin(math.radians(self.orientation[0])), # Roll restoring
            -restoring_torque_factor * math.sin(math.radians(self.orientation[1])), # Pitch restoring
             0.0 # No yaw restoring from buoyancy
        ])

        # Angular drag torque (opposite to angular velocity, in body frame)
        # Simple linear model: T_drag = -C_ad * omega
        torque_angular_drag_body = -self.angular_drag * self.angular_velocity # Assuming omega is in rad/s

        # Total torque in body frame
        net_torque_body = torque_thrusters + torque_buoyancy_body + torque_angular_drag_body

        # --- Update Kinematics ---
        # Linear motion
        acceleration_world = net_force_world / self.mass
        self.velocity += acceleration_world * dt
        self.position += self.velocity * dt

        # Prevent going above surface (y=0)
        if self.position[1] > 0:
            self.position[1] = 0
            if self.velocity[1] > 0:
                self.velocity[1] = 0 # Stop upward velocity at surface

        # Angular motion (using body frame torque)
        angular_acceleration_body = net_torque_body / self.moment_of_inertia
        self.angular_velocity += angular_acceleration_body * dt

        # Update orientation (convert angular velocity from rad/s to deg/s)
        # Simple Euler integration - can lead to gimbal lock, but often sufficient for simulation
        orientation_change_deg = np.degrees(self.angular_velocity) * dt
        self.orientation += orientation_change_deg

        # Normalize orientation angles (optional, but good practice)
        # Yaw: 0 to 360
        self.orientation[2] = self.orientation[2] % 360.0
        # Roll/Pitch: -180 to 180 (or -90 to 90 for pitch if preferred)
        self.orientation[0] = (self.orientation[0] + 180) % 360 - 180
        self.orientation[1] = (self.orientation[1] + 180) % 360 - 180
        # Clamp pitch to +/- 90 to avoid gimbal lock issues if using Euler angles extensively
        # self.orientation[1] = max(-90.0, min(90.0, self.orientation[1]))


        # Update water depth (positive value, based on negative y position)
        self.water_depth = -self.position[1]

        # Return current state
        return {
            "orientation": {
                "roll": self.orientation[0],
                "pitch": self.orientation[1],
                "yaw": self.orientation[2]
            },
            "depth": self.water_depth,
            "position": self.position.tolist(),
            "velocity": self.velocity.tolist(),
            "angular_velocity": np.degrees(self.angular_velocity).tolist() # Return in deg/s
        }


# --- PIDSimulator Class (Modified for BNO055DataProvider) ---
class PIDSimulator:
    """PID simulator focused on visualizing controller behavior using BNO055"""

    def __init__(self):
        # Initialize pygame
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("ROV PID Simulator (BNO055)")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Arial', 16)
        self.large_font = pygame.font.SysFont('Arial', 24, bold=True)

        # Initialize physics model
        self.physics = ROVPhysics()

        # Initialize PID controllers with ROV settings (adjust these!)
        # Gains might need significant tuning based on physics model and BNO055 noise
        self.pid_controllers = {
            # Roll/Pitch often need higher gains due to restoring torque
            'roll': PID_Controller(kp=0.08, ki=0.02, kd=0.05, a=0.7), # P needs to overcome restoring torque
            'pitch': PID_Controller(kp=0.08, ki=0.02, kd=0.05, a=0.7),# D helps dampen oscillations
            'yaw': PID_Controller(kp=0.03, ki=0.005, kd=0.02, a=0.8), # Yaw is usually slower, lower gains
            'depth': PID_Controller(kp=0.5, ki=0.1, kd=0.3, a=0.6)    # Depth needs force against buoyancy/gravity
        }
        # Set tolerances (degrees for angles, meters for depth)
        self.pid_controllers['roll'].tolerance = 1.0
        self.pid_controllers['pitch'].tolerance = 1.0
        self.pid_controllers['yaw'].tolerance = 2.0
        self.pid_controllers['depth'].tolerance = 0.05


        # PID setpoints
        self.setpoints = {
            'roll': 0.0,
            'pitch': 0.0,
            'yaw': 0.0, # Target heading
            'depth': 1.0 # Target depth in meters
        }

        # PID enable/disable flags
        self.pid_enabled = {
            'roll': True,
            'pitch': True,
            'yaw': True,
            'depth': True
        }

        # Manual control inputs (not used in this PID-focused version)
        self.manual_control = {'forward': 0.0, 'strafe': 0.0, 'updown': 0.0, 'yaw': 0.0}

        # Thruster values
        self.thruster_values = [0.0] * 8

        # History for plotting
        self.history_length = 300  # Approx 10 seconds at 30fps
        self.history = {
            'time': [],
            'roll': {'actual': [], 'target': [], 'p': [], 'i': [], 'd': [], 'output': []},
            'pitch': {'actual': [], 'target': [], 'p': [], 'i': [], 'd': [], 'output': []},
            'yaw': {'actual': [], 'target': [], 'p': [], 'i': [], 'd': [], 'output': []},
            'depth': {'actual': [], 'target': [], 'p': [], 'i': [], 'd': [], 'output': []}
        }

        # Current simulation time (for plotting)
        self.sim_time = 0.0

        # Active disturbance (applied directly to physics)
        self.disturbance = {
            'roll_torque': 0.0, # Torque in Nm
            'pitch_torque': 0.0,
            'yaw_torque': 0.0,
            'vertical_force': 0.0 # Force in N
        }

        # Selected controller for adjustment
        self.selected_controller = 'roll'

        # Adjustment mode
        self.adjustment_mode = 'none'  # 'none', 'kp', 'ki', 'kd', 'a', 'setpoint'

        # UI elements (Rects)
        self.plot_rect = pygame.Rect(10, 10, 780, 400)
        self.rov_rect = pygame.Rect(810, 10, 380, 300)
        self.control_rect = pygame.Rect(10, 420, 780, 370)
        self.telemetry_rect = pygame.Rect(810, 320, 380, 470)

        # Render surfaces
        self.plot_surface = pygame.Surface((self.plot_rect.width, self.plot_rect.height))
        self.rov_surface = pygame.Surface((self.rov_rect.width, self.rov_rect.height))
        self.control_surface = pygame.Surface((self.control_rect.width, self.control_rect.height))
        self.telemetry_surface = pygame.Surface((self.telemetry_rect.width, self.telemetry_rect.height))

        # Perturbation settings
        self.perturbation_active = False
        self.perturbation_interval = 5.0  # seconds
        self.last_perturbation_time = 0.0

        # Test pattern settings
        self.test_pattern = []
        self.test_index = 0
        self.test_running = False
        self.test_mode = 'step'  # 'step', 'sine', 'ramp'
        self.generate_test_pattern()

        # Flag for running simulation
        self.running = True

        # BNO055 data provider
        self.imu_provider = None
        self.imu_mode = "simulated" # Default to simulated
        self.use_real_imu = False # Flag to indicate if using hardware data for state
        self.imu_recording = False
        self.record_filename = None

    def generate_test_pattern(self):
        """Generate a test pattern for evaluating PID response"""
        self.test_pattern = []
        duration = 40.0 # Total duration for patterns
        num_steps = 80 # Number of points in pattern

        if self.test_mode == 'step':
            # Step response test for the selected controller
            target_value = 0.0
            if self.selected_controller in ['roll', 'pitch']: target_value = 15.0
            elif self.selected_controller == 'yaw': target_value = 45.0
            elif self.selected_controller == 'depth': target_value = 2.0

            self.test_pattern = [
                {'time': 0.0, 'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0, 'depth': 1.0}, # Initial state
                {'time': 2.0, self.selected_controller: target_value}, # Step up
                {'time': 12.0, self.selected_controller: -target_value}, # Step down
                {'time': 22.0, self.selected_controller: 0.0}, # Back to zero
                {'time': 30.0, 'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0, 'depth': 1.0} # Ensure stable end
            ]
            # Fill missing values with previous state
            last_vals = {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0, 'depth': 1.0}
            for point in self.test_pattern:
                for key in last_vals:
                    if key not in point:
                        point[key] = last_vals[key]
                last_vals.update(point)


        elif self.test_mode == 'sine':
            # Sine wave test for the selected controller
            amplitude = 0.0
            frequency = 0.1 # Hz
            offset = 0.0
            if self.selected_controller in ['roll', 'pitch']: amplitude = 15.0
            elif self.selected_controller == 'yaw': amplitude = 45.0
            elif self.selected_controller == 'depth': amplitude = 1.0; offset = 1.5 # Sine between 0.5 and 2.5m

            for i in range(num_steps + 1):
                t = (i / num_steps) * duration
                value = amplitude * math.sin(2 * math.pi * frequency * t) + offset
                point = {'time': t, 'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0, 'depth': 1.0} # Default state
                point[self.selected_controller] = value
                self.test_pattern.append(point)

        elif self.test_mode == 'ramp':
            # Ramp test for the selected controller
            max_value = 0.0
            if self.selected_controller in ['roll', 'pitch']: max_value = 20.0
            elif self.selected_controller == 'yaw': max_value = 60.0
            elif self.selected_controller == 'depth': max_value = 2.0; offset = 1.0

            ramp_time = duration / 4.0
            for i in range(num_steps + 1):
                t = (i / num_steps) * duration
                value = 0.0
                if t < ramp_time: # Ramp up
                    value = (t / ramp_time) * max_value
                elif t < 2 * ramp_time: # Ramp down
                    value = max_value - ((t - ramp_time) / ramp_time) * max_value
                elif t < 3 * ramp_time: # Ramp down (negative)
                    value = - ((t - 2*ramp_time) / ramp_time) * max_value
                else: # Ramp up to zero
                    value = -max_value + ((t - 3*ramp_time) / ramp_time) * max_value

                point = {'time': t, 'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0, 'depth': 1.0} # Default state
                if self.selected_controller == 'depth':
                     point[self.selected_controller] = value + offset
                else:
                     point[self.selected_controller] = value
                self.test_pattern.append(point)

        logger.info(f"Generated '{self.test_mode}' test pattern for '{self.selected_controller}' with {len(self.test_pattern)} points.")


    def start_test(self):
        """Start the test pattern"""
        if not self.test_pattern:
            logger.warning("No test pattern generated. Cannot start test.")
            return

        self.test_running = True
        self.test_index = 0
        self.sim_time = 0.0 # Reset simulation time for plot clarity
        # Reset physics to a known state
        self.physics = ROVPhysics()
        self.physics.position[1] = -self.test_pattern[0].get('depth', 1.0) # Start at initial depth
        self.physics.water_depth = -self.physics.position[1]

        # Reset PID controllers (clear integral, errors)
        for controller in self.pid_controllers.values():
            controller.area = 0.0
            controller.previous_error = 0.0
            controller.previous_filter_estimate = 0.0
            controller.runtime.reset()

        # Reset history
        self.history = {
            'time': [],
            'roll': {'actual': [], 'target': [], 'p': [], 'i': [], 'd': [], 'output': []},
            'pitch': {'actual': [], 'target': [], 'p': [], 'i': [], 'd': [], 'output': []},
            'yaw': {'actual': [], 'target': [], 'p': [], 'i': [], 'd': [], 'output': []},
            'depth': {'actual': [], 'target': [], 'p': [], 'i': [], 'd': [], 'output': []}
        }
        logger.info(f"Starting '{self.test_mode}' test for '{self.selected_controller}'.")

    def update_test_setpoints(self, current_sim_time):
        """Update setpoints based on current test pattern time"""
        if not self.test_running or not self.test_pattern:
            return

        # Find the segment of the test pattern corresponding to the current time
        target_pattern = self.test_pattern[0] # Default to first point
        for i in range(len(self.test_pattern) - 1):
            p1 = self.test_pattern[i]
            p2 = self.test_pattern[i+1]
            if p1['time'] <= current_sim_time < p2['time']:
                # Interpolate between p1 and p2 for smoother transitions (optional)
                # For simplicity, just use the setpoints from p1 until p2 time is reached
                target_pattern = p1
                self.test_index = i
                break
            elif current_sim_time >= self.test_pattern[-1]['time']:
                 # Hold the last setpoint if time exceeds pattern duration
                 target_pattern = self.test_pattern[-1]
                 self.test_index = len(self.test_pattern) - 1
                 # Option to stop the test automatically after a delay
                 if current_sim_time > self.test_pattern[-1]['time'] + 3.0: # Hold for 3s then stop
                     logger.info("Test pattern completed.")
                     self.test_running = False
                 break
        else:
             # If loop finishes without break, we are likely before the first point or exactly on the last
             if current_sim_time >= self.test_pattern[-1]['time']:
                 target_pattern = self.test_pattern[-1]
                 self.test_index = len(self.test_pattern) - 1
             else:
                 target_pattern = self.test_pattern[0]
                 self.test_index = 0


        # Update setpoints from the target pattern segment
        self.setpoints['roll'] = target_pattern.get('roll', self.setpoints['roll'])
        self.setpoints['pitch'] = target_pattern.get('pitch', self.setpoints['pitch'])
        self.setpoints['yaw'] = target_pattern.get('yaw', self.setpoints['yaw'])
        self.setpoints['depth'] = target_pattern.get('depth', self.setpoints['depth'])


    def run(self):
        """Run the simulator main loop"""
        prev_time = time.time()

        while self.running:
            # Calculate dt
            current_time_real = time.time()
            dt = current_time_real - prev_time
            # Clamp dt to avoid large jumps if debugging or pausing
            dt = min(dt, 0.1) # Max dt of 100ms
            prev_time = current_time_real

            # Process events
            self.process_events()

            # Update simulation time
            self.sim_time += dt

            # If test is running, update setpoints based on sim_time
            if self.test_running:
                self.update_test_setpoints(self.sim_time)

            # Update physics model and PID control
            self.update_state_and_control(dt)

            # Apply random perturbations if active
            if self.perturbation_active:
                self.apply_perturbations(dt)

            # Store history for plotting
            self.update_history()

            # Render screen
            self.render()

            # Cap frame rate
            self.clock.tick(60) # Target 60 FPS

        # Cleanup
        pygame.quit()
        if self.imu_provider:
            self.imu_provider.stop()
        logger.info("Simulator exited.")


    def process_events(self):
        """Process user input events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False

                # Controller selection
                elif event.key == pygame.K_1: self.selected_controller = 'roll'; self.generate_test_pattern()
                elif event.key == pygame.K_2: self.selected_controller = 'pitch'; self.generate_test_pattern()
                elif event.key == pygame.K_3: self.selected_controller = 'yaw'; self.generate_test_pattern()
                elif event.key == pygame.K_4: self.selected_controller = 'depth'; self.generate_test_pattern()

                # Toggle PID controllers
                elif event.key == pygame.K_r: self.pid_enabled['roll'] = not self.pid_enabled['roll']
                elif event.key == pygame.K_p: self.pid_enabled['pitch'] = not self.pid_enabled['pitch']
                elif event.key == pygame.K_y: self.pid_enabled['yaw'] = not self.pid_enabled['yaw']
                elif event.key == pygame.K_d: self.pid_enabled['depth'] = not self.pid_enabled['depth']

                # Reset physics and PIDs
                elif event.key == pygame.K_SPACE:
                    logger.info("Resetting physics and PID states.")
                    self.physics = ROVPhysics()
                    self.sim_time = 0.0
                    self.test_running = False # Stop test on reset
                    # Reset PID controllers
                    for controller in self.pid_controllers.values():
                        controller.area = 0.0
                        controller.previous_error = 0.0
                        controller.previous_filter_estimate = 0.0
                        controller.runtime.reset()
                    # Reset history
                    self.history = {k: [] if k == 'time' else {sk: [] for sk in v} for k, v in self.history.items()}


                # Parameter adjustment mode
                elif event.key == pygame.K_k: self.adjustment_mode = 'kp'
                elif event.key == pygame.K_i: self.adjustment_mode = 'ki'
                elif event.key == pygame.K_b: self.adjustment_mode = 'kd' # 'B' for Kd
                elif event.key == pygame.K_f: self.adjustment_mode = 'a' # 'F' for filter alpha
                elif event.key == pygame.K_s: self.adjustment_mode = 'setpoint'
                elif event.key == pygame.K_RETURN: self.adjustment_mode = 'none'

                # Adjustment values (fine and coarse)
                elif event.key == pygame.K_UP: self.adjust_parameter(0.1) # Coarse up
                elif event.key == pygame.K_DOWN: self.adjust_parameter(-0.1) # Coarse down
                elif event.key == pygame.K_RIGHT: self.adjust_parameter(0.01) # Fine up
                elif event.key == pygame.K_LEFT: self.adjust_parameter(-0.01) # Fine down

                # Disturbance commands (apply torque/force)
                elif event.key == pygame.K_q: self.disturbance['roll_torque'] = 0.5 # Nm
                elif event.key == pygame.K_w: self.disturbance['pitch_torque'] = 0.5
                elif event.key == pygame.K_e: self.disturbance['yaw_torque'] = 0.3
                elif event.key == pygame.K_a: self.disturbance['roll_torque'] = -0.5
                # S key used for setpoint adjustment, use Z for pitch down disturbance
                elif event.key == pygame.K_z: self.disturbance['pitch_torque'] = -0.5
                # D key used for depth toggle, use X for yaw right disturbance
                elif event.key == pygame.K_x: self.disturbance['yaw_torque'] = -0.3
                # Use C/V for depth disturbance
                elif event.key == pygame.K_c: self.disturbance['vertical_force'] = 5.0 # Newtons
                elif event.key == pygame.K_v: self.disturbance['vertical_force'] = -5.0

                # Toggle perturbation
                elif event.key == pygame.K_t:
                    self.perturbation_active = not self.perturbation_active
                    logger.info(f"Random perturbations {'activated' if self.perturbation_active else 'deactivated'}.")

                # Test pattern controls
                elif event.key == pygame.K_F1:
                    self.test_mode = 'step'; self.generate_test_pattern()
                    logger.info("Set test mode to 'step'. Press F5 to run.")
                elif event.key == pygame.K_F2:
                    self.test_mode = 'sine'; self.generate_test_pattern()
                    logger.info("Set test mode to 'sine'. Press F5 to run.")
                elif event.key == pygame.K_F3:
                    self.test_mode = 'ramp'; self.generate_test_pattern()
                    logger.info("Set test mode to 'ramp'. Press F5 to run.")
                elif event.key == pygame.K_F5:
                    self.start_test()

                # IMU data source control
                elif event.key == pygame.K_F6:
                    if bno055_available:
                        new_mode = "hardware" if self.imu_mode == "simulated" else "simulated"
                        if self.initialize_imu_provider(mode=new_mode):
                            logger.info(f"Switched to {new_mode} BNO055 data source.")
                            # Reset physics/PIDs when switching modes? Optional.
                            # self.physics = ROVPhysics() # Uncomment to reset state on mode switch
                    else:
                        logger.warning("Cannot switch to hardware mode: BNO055 module not available.")

                # Data recording control
                elif event.key == pygame.K_F7:
                    if not self.imu_recording and self.imu_provider:
                        self.imu_recording = True
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        self.record_filename = f"bno055_rec_{self.imu_mode}_{timestamp}.csv"
                        # Start a recording thread
                        threading.Thread(
                            target=self.record_session_thread,
                            args=(self.record_filename, 30),  # Record for 30 seconds
                            daemon=True
                        ).start()
                    elif self.imu_recording:
                        logger.info("Recording already in progress.")
                    else:
                         logger.warning("Cannot record: IMU provider not initialized.")

                # Load IMU recording (Placeholder)
                elif event.key == pygame.K_F8:
                    logger.warning("Loading IMU recording not implemented yet.")
                    # TODO: Add file dialog and playback logic

            elif event.type == pygame.KEYUP:
                # Clear disturbances when key is released
                if event.key in [pygame.K_q, pygame.K_a]: self.disturbance['roll_torque'] = 0.0
                elif event.key in [pygame.K_w, pygame.K_z]: self.disturbance['pitch_torque'] = 0.0 # Z used for pitch down
                elif event.key in [pygame.K_e, pygame.K_x]: self.disturbance['yaw_torque'] = 0.0 # X used for yaw right
                elif event.key in [pygame.K_c, pygame.K_v]: self.disturbance['vertical_force'] = 0.0


    def adjust_parameter(self, amount_coarse):
        """Adjust the selected parameter by fine or coarse amount"""
        # Determine step size based on parameter type
        param_type = self.adjustment_mode
        controller = self.pid_controllers[self.selected_controller]

        fine_multiplier = 0.1 # Fine adjustment is 1/10th of coarse
        amount = amount_coarse * fine_multiplier if pygame.key.get_pressed()[pygame.K_LSHIFT] or pygame.key.get_pressed()[pygame.K_RSHIFT] else amount_coarse

        if param_type == 'kp':
            controller.kp = max(0.0, controller.kp + amount)
            logger.debug(f"Adjusted {self.selected_controller} Kp to {controller.kp:.4f}")
        elif param_type == 'ki':
            controller.ki = max(0.0, controller.ki + amount)
            logger.debug(f"Adjusted {self.selected_controller} Ki to {controller.ki:.4f}")
        elif param_type == 'kd':
            controller.kd = max(0.0, controller.kd + amount)
            logger.debug(f"Adjusted {self.selected_controller} Kd to {controller.kd:.4f}")
        elif param_type == 'a':
            controller.a = max(0.0, min(1.0, controller.a + amount))
            logger.debug(f"Adjusted {self.selected_controller} Filter Alpha to {controller.a:.4f}")
        elif param_type == 'setpoint':
            # Adjust setpoint more significantly
            setpoint_step = 1.0 if self.selected_controller != 'depth' else 0.1
            self.setpoints[self.selected_controller] += amount * setpoint_step * 10 # Make setpoint changes larger
            # Clamp depth setpoint
            if self.selected_controller == 'depth':
                self.setpoints['depth'] = max(0.0, self.setpoints['depth'])
            logger.debug(f"Adjusted {self.selected_controller} Setpoint to {self.setpoints[self.selected_controller]:.2f}")


    def apply_perturbations(self, dt):
        """Apply random perturbations to simulate environmental effects"""
        current_time = self.sim_time # Use simulation time

        # Apply a new perturbation every interval
        if current_time - self.last_perturbation_time > self.perturbation_interval:
            self.last_perturbation_time = current_time

            # Apply random torques (directly modify angular velocity for impulse effect)
            perturb_roll_torque = (np.random.random() - 0.5) * 0.8 # Nm
            perturb_pitch_torque = (np.random.random() - 0.5) * 0.8 # Nm
            perturb_yaw_torque = (np.random.random() - 0.5) * 0.5 # Nm
            # Apply as impulse (change in angular velocity = torque * dt / I)
            # Simplified: Add directly to angular velocity (adjust magnitude)
            self.physics.angular_velocity += np.array([
                 np.radians((np.random.random() - 0.5) * 10.0), # Roll deg/s impulse
                 np.radians((np.random.random() - 0.5) * 10.0), # Pitch deg/s impulse
                 np.radians((np.random.random() - 0.5) * 15.0)  # Yaw deg/s impulse
            ])


            # Apply random vertical force impulse
            if np.random.random() < 0.5:  # 50% chance
                 perturb_force = (np.random.random() - 0.5) * 10.0 # N impulse
                 # Apply as impulse (change in velocity = force * dt / m)
                 # Simplified: Add directly to velocity
                 self.physics.velocity[1] += perturb_force / self.physics.mass


    def update_state_and_control(self, dt):
        """Update ROV state (from IMU or physics) and apply PID control"""

        current_state = {}
        # Get data from the provider (either real BNO055 or simulated)
        if self.imu_provider:
            imu_data = self.imu_provider.get_latest_data()
            current_state['roll'] = imu_data['roll']
            current_state['pitch'] = imu_data['pitch']
            current_state['yaw'] = imu_data['yaw']
            # Depth always comes from physics model, even if orientation is from BNO055
            current_state['depth'] = self.physics.water_depth
            current_state['timestamp'] = imu_data['timestamp']

            # If using hardware, optionally override physics orientation
            if self.use_real_imu:
                self.physics.orientation[0] = current_state['roll']
                self.physics.orientation[1] = current_state['pitch']
                # Handle yaw wrapping carefully if needed, BNO055 provides 0-360
                self.physics.orientation[2] = current_state['yaw']
                # We don't get velocity from BNO055, so physics still calculates that
        else:
            # If no provider, use physics state directly
            current_state['roll'] = self.physics.orientation[0]
            current_state['pitch'] = self.physics.orientation[1]
            current_state['yaw'] = self.physics.orientation[2]
            current_state['depth'] = self.physics.water_depth
            current_state['timestamp'] = self.sim_time


        # Apply manual disturbances directly to physics model
        # These are added to the net force/torque calculations within physics.update
        self.physics.external_force = np.array([0.0, self.disturbance['vertical_force'], 0.0])
        self.physics.external_torque = np.array([
            self.disturbance['roll_torque'],
            self.disturbance['pitch_torque'],
            self.disturbance['yaw_torque']
        ])


        # Calculate PID corrections based on current state and setpoints
        pid_outputs = {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0, 'depth': 0.0}

        # Use current state from IMU/Physics for PID input
        current_roll = current_state['roll']
        current_pitch = current_state['pitch']
        current_yaw = current_state['yaw'] # Assuming 0-360 range
        current_depth = current_state['depth']

        target_yaw = self.setpoints['yaw']

        # Handle Yaw Wrap-Around (calculate shortest angle difference)
        yaw_error = target_yaw - current_yaw
        if yaw_error > 180.0:
            yaw_error -= 360.0
        elif yaw_error <= -180.0:
            yaw_error += 360.0
        # Now use yaw_error directly in PID calculation (target becomes current + error)
        target_yaw_for_pid = current_yaw + yaw_error


        if self.pid_enabled['roll']:
            pid_outputs['roll'] = self.pid_controllers['roll'].PID_Power(
                current_roll, self.setpoints['roll'])

        if self.pid_enabled['pitch']:
            pid_outputs['pitch'] = self.pid_controllers['pitch'].PID_Power(
                current_pitch, self.setpoints['pitch'])

        if self.pid_enabled['yaw']:
             # Use the adjusted target yaw for PID calculation
            pid_outputs['yaw'] = self.pid_controllers['yaw'].PID_Power(
                current_yaw, target_yaw_for_pid) # Pass current and adjusted target

        if self.pid_enabled['depth']:
            pid_outputs['depth'] = self.pid_controllers['depth'].PID_Power(
                current_depth, self.setpoints['depth'])

        # Combine PID outputs into the 6DOF control vector for arcadeDrive6
        # [x, y, z, roll, pitch, yaw]
        # x, y are manual/joystick inputs (set to 0 here)
        # z, roll, pitch, yaw are PID outputs
        control_vector = [
            0.0, # Manual Forward/Backward
            0.0, # Manual Strafe
            pid_outputs['depth'], # PID Up/Down (Depth)
            pid_outputs['roll'],  # PID Roll correction
            pid_outputs['pitch'], # PID Pitch correction
            pid_outputs['yaw']    # PID Yaw correction
        ]

        # Calculate thruster values using arcadeDrive6
        motor_values = arcadeDrive6(control_vector)
        self.thruster_values = motor_values

        # Update physics model using calculated thruster forces
        # The physics model now integrates forces/torques over dt
        self.physics.update_thruster_forces(motor_values)
        physics_state = self.physics.update(dt)

        # If NOT using real IMU, update the displayed state from physics
        # If using real IMU, the state was already updated at the start of this function
        if not self.use_real_imu:
             current_state['roll'] = physics_state['orientation']['roll']
             current_state['pitch'] = physics_state['orientation']['pitch']
             current_state['yaw'] = physics_state['orientation']['yaw']
             current_state['depth'] = physics_state['depth']
             # Update physics depth variable as well
             self.physics.water_depth = physics_state['depth']


    def update_history(self):
        """Update the history arrays for plotting"""
        # Use simulation time for the plot's x-axis
        current_plot_time = self.sim_time
        self.history['time'].append(current_plot_time)

        # Get current actual values (might be from IMU or physics)
        if self.use_real_imu and self.imu_provider:
             latest_data = self.imu_provider.current_data # Use the latest read data
             actual_roll = latest_data['roll']
             actual_pitch = latest_data['pitch']
             actual_yaw = latest_data['yaw']
             actual_depth = self.physics.water_depth # Depth always from physics
        else:
             actual_roll = self.physics.orientation[0]
             actual_pitch = self.physics.orientation[1]
             actual_yaw = self.physics.orientation[2]
             actual_depth = self.physics.water_depth

        actual_values = {
            'roll': actual_roll,
            'pitch': actual_pitch,
            'yaw': actual_yaw,
            'depth': actual_depth
        }

        # Add current values for each controller
        for axis in self.pid_controllers:
            controller = self.pid_controllers[axis]
            hist_axis = self.history[axis]

            # Add actual and target values
            hist_axis['actual'].append(actual_values[axis])
            hist_axis['target'].append(self.setpoints[axis])

            # Add PID components and output
            hist_axis['p'].append(controller.P)
            hist_axis['i'].append(controller.I)
            hist_axis['d'].append(controller.D)
            hist_axis['output'].append(controller.P + controller.I + controller.D)

        # Trim history to max length
        if len(self.history['time']) > self.history_length:
            self.history['time'].pop(0) # Remove oldest time
            for axis in self.pid_controllers:
                for key in self.history[axis]:
                    if self.history[axis][key]: # Check if list is not empty
                        self.history[axis][key].pop(0) # Remove oldest value


    def render(self):
        """Render the simulator display"""
        # Fill background
        self.screen.fill(BG_COLOR)

        # Render each section onto its surface
        self.render_plot()
        self.render_rov()
        self.render_controls()
        self.render_telemetry()

        # Blit all surfaces to the main screen
        self.screen.blit(self.plot_surface, self.plot_rect.topleft)
        self.screen.blit(self.rov_surface, self.rov_rect.topleft)
        self.screen.blit(self.control_surface, self.control_rect.topleft)
        self.screen.blit(self.telemetry_surface, self.telemetry_rect.topleft)

        # Render borders around sections
        pygame.draw.rect(self.screen, TEXT_COLOR, self.plot_rect, 1)
        pygame.draw.rect(self.screen, TEXT_COLOR, self.rov_rect, 1)
        pygame.draw.rect(self.screen, TEXT_COLOR, self.control_rect, 1)
        pygame.draw.rect(self.screen, TEXT_COLOR, self.telemetry_rect, 1)

        # Update display
        pygame.display.flip()

    def render_plot(self):
        """Render the PID plot for the selected controller"""
        # Clear surface
        self.plot_surface.fill(PLOT_BG_COLOR)

        # Draw title
        title = f"{self.selected_controller.capitalize()} Controller Response ({'Test Running' if self.test_running else 'Manual'})"
        title_surf = self.large_font.render(title, True, TEXT_COLOR)
        self.plot_surface.blit(title_surf, (10, 10))

        # Set up plot area
        plot_area = pygame.Rect(60, 50, self.plot_rect.width - 80, self.plot_rect.height - 100)
        pygame.draw.rect(self.plot_surface, (50, 50, 60), plot_area, 1) # Border

        # Draw grid lines
        grid_spacing_x = plot_area.width / 10
        grid_spacing_y = plot_area.height / 8
        for i in range(1, 10): # Vertical grid lines
            x = plot_area.left + i * grid_spacing_x
            pygame.draw.line(self.plot_surface, GRID_COLOR, (x, plot_area.top), (x, plot_area.bottom))
        for i in range(1, 8): # Horizontal grid lines
            y = plot_area.top + i * grid_spacing_y
            pygame.draw.line(self.plot_surface, GRID_COLOR, (plot_area.left, y), (plot_area.right, y))


        # Plot the data if we have enough points
        if len(self.history['time']) > 1:
            axis_data = self.history[self.selected_controller]
            time_data = self.history['time']

            # Determine time range for the plot (last N seconds or full test duration)
            plot_duration = 15.0 # Show last 15 seconds by default
            if self.test_running and self.test_pattern:
                 # If test is long, maybe limit view? Or show full test?
                 # Let's stick to a fixed window for now.
                 pass

            latest_time = time_data[-1]
            start_time = max(0, latest_time - plot_duration)
            current_time_range = latest_time - start_time
            if current_time_range < 1e-6: current_time_range = 1.0 # Avoid division by zero

            # Find min/max values within the visible time range for Y axis scaling
            min_y, max_y = float('inf'), float('-inf')
            indices_in_range = [i for i, t in enumerate(time_data) if t >= start_time]

            if indices_in_range:
                first_idx = indices_in_range[0]
                # Check actual and target values for range
                for key in ['actual', 'target']:
                    if axis_data[key]:
                        visible_data = axis_data[key][first_idx:]
                        if visible_data:
                            min_y = min(min_y, min(visible_data))
                            max_y = max(max_y, max(visible_data))

                # Optionally include PID components in auto-scaling (can make plot jumpy)
                # show_pid_components = pygame.key.get_pressed()[pygame.K_LCTRL]
                # if show_pid_components:
                #     for key in ['p', 'i', 'd', 'output']:
                #         if axis_data[key]:
                #             visible_data = axis_data[key][first_idx:]
                #             if visible_data:
                #                 min_y = min(min_y, min(visible_data))
                #                 max_y = max(max_y, max(visible_data))

            # Handle cases where data is flat or missing
            if min_y == float('inf'): min_y, max_y = -1.0, 1.0
            if max_y - min_y < 0.1: # Add padding if range is too small
                mid = (max_y + min_y) / 2.0
                max_y = mid + 0.5
                min_y = mid - 0.5
            else: # Add padding to range
                padding = (max_y - min_y) * 0.1
                min_y -= padding
                max_y += padding

            y_value_range = max_y - min_y
            if y_value_range < 1e-6: y_value_range = 1.0 # Avoid division by zero


            # --- Plotting ---
            colors = {
                'actual': (255, 255, 0),    # Yellow
                'target': (0, 255, 0),      # Green
                'p': (255, 100, 100),       # Light Red
                'i': (100, 100, 255),       # Light Blue
                'd': (255, 100, 255),       # Light Magenta
                'output': (255, 255, 255)   # White
            }
            show_pid_components = pygame.key.get_pressed()[pygame.K_LCTRL]

            for key, color in colors.items():
                # Skip PID components if Ctrl not pressed
                if not show_pid_components and key in ('p', 'i', 'd', 'output'):
                    continue

                if key in axis_data and len(axis_data[key]) > 1:
                    points = []
                    # Iterate through indices that are within the time range
                    for i in indices_in_range:
                        t = time_data[i]
                        v = axis_data[key][i]
                        # Map time and value to screen coordinates
                        x = plot_area.left + ((t - start_time) / current_time_range) * plot_area.width
                        y = plot_area.bottom - ((v - min_y) / y_value_range) * plot_area.height
                        # Clip points to be within the plot area vertically
                        y = max(plot_area.top, min(plot_area.bottom, y))
                        points.append((x, y))

                    # Draw lines if we have points
                    if len(points) > 1:
                        pygame.draw.lines(self.plot_surface, color, False, points, 2 if key in ['actual', 'target'] else 1)

            # Draw Y-axis labels
            num_y_labels = 5
            for i in range(num_y_labels + 1):
                val = min_y + (i / num_y_labels) * y_value_range
                y = plot_area.bottom - i * (plot_area.height / num_y_labels)
                label_text = f"{val:.1f}"
                label_surf = self.font.render(label_text, True, TEXT_COLOR)
                self.plot_surface.blit(label_surf, (plot_area.left - 45, y - 8))

            # Draw X-axis labels (Time)
            num_x_labels = 5
            for i in range(num_x_labels + 1):
                 t = start_time + (i / num_x_labels) * current_time_range
                 x = plot_area.left + i * (plot_area.width / num_x_labels)
                 label_text = f"{t:.1f}s"
                 label_surf = self.font.render(label_text, True, TEXT_COLOR)
                 self.plot_surface.blit(label_surf, (x - 15, plot_area.bottom + 5))


        # Draw legend
        legend_x = plot_area.left
        legend_y = plot_area.bottom + 30
        legend_items = [('Actual', colors['actual']), ('Target', colors['target'])]
        if show_pid_components:
            legend_items.extend([
                ('P Term', colors['p']), ('I Term', colors['i']),
                ('D Term', colors['d']), ('Output', colors['output'])
            ])

        for name, color in legend_items:
            pygame.draw.rect(self.plot_surface, color, (legend_x, legend_y, 15, 10))
            text = self.font.render(name, True, TEXT_COLOR)
            self.plot_surface.blit(text, (legend_x + 20, legend_y - 2))
            legend_x += text.get_width() + 40 # Adjust spacing


    def render_rov(self):
        """Render the ROV visualization (Top-down, Roll/Pitch, Depth)"""
        # Clear surface
        self.rov_surface.fill(PLOT_BG_COLOR)

        # Draw title
        title = "ROV Orientation & Depth"
        title_surf = self.large_font.render(title, True, TEXT_COLOR)
        self.rov_surface.blit(title_surf, (10, 10))

        # --- Top-Down View (Yaw) ---
        top_view_center_x = self.rov_rect.width * 0.3
        top_view_center_y = self.rov_rect.height * 0.45
        rov_draw_width = ROV_WIDTH * 0.6
        rov_draw_depth = ROV_DEPTH * 0.6

        yaw_rect = pygame.Rect(
            top_view_center_x - rov_draw_width / 2,
            top_view_center_y - rov_draw_depth / 2,
            rov_draw_width, rov_draw_depth
        )

        # Get current yaw from physics model
        yaw_rad = math.radians(self.physics.orientation[2])
        cos_yaw = math.cos(yaw_rad)
        sin_yaw = math.sin(yaw_rad)

        # Define corners relative to center
        corners_rel = [
            (-rov_draw_width / 2, -rov_draw_depth / 2), # Front Left
            (+rov_draw_width / 2, -rov_draw_depth / 2), # Front Right
            (+rov_draw_width / 2, +rov_draw_depth / 2), # Back Right
            (-rov_draw_width / 2, +rov_draw_depth / 2)  # Back Left
        ]

        # Rotate corners
        rotated_corners = []
        for x, y in corners_rel:
            rotated_x = x * cos_yaw - y * sin_yaw + top_view_center_x
            rotated_y = x * sin_yaw + y * cos_yaw + top_view_center_y
            rotated_corners.append((rotated_x, rotated_y))

        # Draw rotated rectangle (ROV body)
        pygame.draw.polygon(self.rov_surface, (0, 100, 200), rotated_corners)
        pygame.draw.polygon(self.rov_surface, TEXT_COLOR, rotated_corners, 1) # Outline

        # Draw direction indicator (line from center to front mid)
        front_mid_x = (rotated_corners[0][0] + rotated_corners[1][0]) / 2
        front_mid_y = (rotated_corners[0][1] + rotated_corners[1][1]) / 2
        pygame.draw.line(self.rov_surface, (255, 0, 0),
                        (top_view_center_x, top_view_center_y),
                        (front_mid_x, front_mid_y), 3)

        # Draw North reference line
        north_line_end_x = top_view_center_x
        north_line_end_y = top_view_center_y - rov_draw_depth * 0.7
        pygame.draw.line(self.rov_surface, (200, 200, 200), (top_view_center_x, top_view_center_y), (north_line_end_x, north_line_end_y), 1)
        north_text = self.font.render("N", True, (200, 200, 200))
        self.rov_surface.blit(north_text, (north_line_end_x - 5, north_line_end_y - 15))


        # --- Roll/Pitch Indicator (Artificial Horizon) ---
        horizon_center_x = self.rov_rect.width * 0.75
        horizon_center_y = self.rov_rect.height * 0.45
        radius = 50

        # Draw outer circle
        pygame.draw.circle(self.rov_surface, (50, 50, 60), (horizon_center_x, horizon_center_y), radius, 1)

        # Get roll and pitch from physics model
        roll_rad = math.radians(self.physics.orientation[0])
        pitch_deg = self.physics.orientation[1] # Use degrees for pitch offset calculation

        # Calculate pitch offset (how much the horizon moves up/down)
        # Map pitch range (-90 to +90) to vertical movement within the circle
        pitch_offset = (pitch_deg / 90.0) * radius * 0.8 # Scale factor
        pitch_offset = max(-radius*0.9, min(radius*0.9, pitch_offset)) # Clamp offset

        # Calculate horizon line endpoints, rotated by roll
        horizon_length = radius * 1.5 # Make line wider than circle
        cos_roll = math.cos(roll_rad)
        sin_roll = math.sin(roll_rad)

        # Center of the horizon line, adjusted by pitch
        line_center_y = horizon_center_y + pitch_offset

        # Endpoints relative to line center
        dx = horizon_length / 2
        dy = 0
        # Rotate endpoints by roll
        x1 = horizon_center_x + (-dx * cos_roll - dy * sin_roll)
        y1 = line_center_y   + (-dx * sin_roll + dy * cos_roll)
        x2 = horizon_center_x + (dx * cos_roll - dy * sin_roll)
        y2 = line_center_y   + (dx * sin_roll + dy * cos_roll)

        # Clip the horizon line to the circle's bounds for drawing sky/ground
        clip_rect = pygame.Rect(horizon_center_x - radius, horizon_center_y - radius, 2*radius, 2*radius)
        self.rov_surface.set_clip(clip_rect)

        # Draw sky (blue) and ground (brown) based on horizon line
        # Create points for polygons covering the circle area above/below the line
        points_sky = [(x1, y1), (x2, y2)]
        points_ground = [(x1, y1), (x2, y2)]

        # Add points far above/below to complete the polygons
        far_y = radius * 2
        points_sky.extend([(x2, y2 - far_y), (x1, y1 - far_y)]) # Above line
        points_ground.extend([(x2, y2 + far_y), (x1, y1 + far_y)]) # Below line

        pygame.draw.polygon(self.rov_surface, (100, 150, 255), points_sky) # Sky blue
        pygame.draw.polygon(self.rov_surface, (139, 69, 19), points_ground) # Ground brown

        # Draw the horizon line itself
        pygame.draw.line(self.rov_surface, TEXT_COLOR, (x1, y1), (x2, y2), 2)

        # Remove clipping
        self.rov_surface.set_clip(None)

        # Draw fixed aircraft symbol (center mark)
        symbol_size = 10
        pygame.draw.line(self.rov_surface, (255, 255, 0),
                        (horizon_center_x - symbol_size, horizon_center_y),
                        (horizon_center_x + symbol_size, horizon_center_y), 2)
        pygame.draw.line(self.rov_surface, (255, 255, 0),
                        (horizon_center_x, horizon_center_y - symbol_size // 2),
                        (horizon_center_x, horizon_center_y + symbol_size // 2), 2)


        # --- Depth Indicator ---
        depth_bar_width = 20
        depth_bar_height = self.rov_rect.height * 0.7
        depth_bar_x = self.rov_rect.width * 0.9 - depth_bar_width / 2
        depth_bar_y = (self.rov_rect.height - depth_bar_height) / 2

        depth_rect = pygame.Rect(depth_bar_x, depth_bar_y, depth_bar_width, depth_bar_height)
        pygame.draw.rect(self.rov_surface, (50, 50, 60), depth_rect, 1) # Border

        # Calculate depth bar fill height
        max_display_depth = 5.0 # Max depth shown on the scale
        current_depth = self.physics.water_depth
        depth_pct = min(1.0, max(0.0, current_depth / max_display_depth))
        fill_height = int(depth_bar_height * depth_pct)

        # Draw depth fill (from top down)
        fill_rect = pygame.Rect(
            depth_rect.left + 1,
            depth_rect.top + 1,
            depth_rect.width - 2,
            fill_height - 1
        )
        pygame.draw.rect(self.rov_surface, (0, 100, 255), fill_rect)

        # Draw depth scale markings and labels
        num_depth_marks = 6 # 0m to 5m
        for i in range(num_depth_marks):
            depth_val = i * (max_display_depth / (num_depth_marks - 1))
            mark_y = depth_rect.top + (depth_val / max_display_depth) * depth_bar_height
            pygame.draw.line(self.rov_surface, TEXT_COLOR,
                           (depth_rect.left - 5, mark_y),
                           (depth_rect.left, mark_y), 1)

            depth_text = self.font.render(f"{depth_val:.1f}", True, TEXT_COLOR)
            self.rov_surface.blit(depth_text, (depth_rect.left - 35, mark_y - 8))

        # Draw current depth value text
        depth_val_text = self.font.render(f"{current_depth:.2f}m", True, (0, 255, 255))
        self.rov_surface.blit(depth_val_text, (depth_rect.left - 40, depth_rect.bottom + 5))


        # --- Draw Orientation Values Text ---
        roll_text = self.font.render(f"Roll: {self.physics.orientation[0]:6.1f}°", True, TEXT_COLOR)
        pitch_text = self.font.render(f"Pitch: {self.physics.orientation[1]:5.1f}°", True, TEXT_COLOR)
        yaw_text = self.font.render(f"Yaw: {self.physics.orientation[2]:7.1f}°", True, TEXT_COLOR)

        text_y_start = self.rov_rect.height * 0.8
        self.rov_surface.blit(roll_text, (10, text_y_start))
        self.rov_surface.blit(pitch_text, (10, text_y_start + 20))
        self.rov_surface.blit(yaw_text, (10, text_y_start + 40))


    def render_controls(self):
        """Render the PID control panel and help"""
        # Clear surface
        self.control_surface.fill(PLOT_BG_COLOR)

        # Draw title
        title = "PID Controller Settings"
        title_surf = self.large_font.render(title, True, TEXT_COLOR)
        self.control_surface.blit(title_surf, (10, 10))

        # --- Draw controller settings ---
        x_start = 20
        y_start = 50
        col_width = 190
        row_height = 20
        param_y_offset = 25

        controllers = ["roll", "pitch", "yaw", "depth"]
        for i, name in enumerate(controllers):
            controller = self.pid_controllers[name]
            enabled = self.pid_enabled[name]
            x_pos = x_start + i * col_width

            # Highlight selected controller background
            if name == self.selected_controller:
                highlight_rect = pygame.Rect(x_pos - 10, y_start - 5, col_width - 10, 165)
                pygame.draw.rect(self.control_surface, (50, 50, 100), highlight_rect, 0, 5)

            # Controller name and enable status (Toggle Key)
            toggle_keys = {'roll': 'R', 'pitch': 'P', 'yaw': 'Y', 'depth': 'D'}
            header_text = f"{i+1}: {name.capitalize()} ({toggle_keys[name]})"
            header_color = TEXT_COLOR if enabled else (100, 100, 100)
            controller_header = self.font.render(header_text, True, header_color)
            self.control_surface.blit(controller_header, (x_pos, y_start))
            status_text = "[ON]" if enabled else "[OFF]"
            status_color = (0, 255, 0) if enabled else (255, 0, 0)
            status_surf = self.font.render(status_text, True, status_color)
            self.control_surface.blit(status_surf, (x_pos + controller_header.get_width() + 5, y_start))


            # PID parameters (Value and Adjustment Key)
            param_color = (200, 200, 200)
            highlight_color = (255, 255, 0) # Yellow for active adjustment

            params_to_show = [
                ('Kp (K)', 'kp', controller.kp),
                ('Ki (I)', 'ki', controller.ki),
                ('Kd (B)', 'kd', controller.kd), # B for Kd key
                ('Filt (F)', 'a', controller.a), # F for Filter key
            ]

            current_y = y_start + param_y_offset
            for label, mode_key, value in params_to_show:
                text_color = highlight_color if name == self.selected_controller and self.adjustment_mode == mode_key else param_color
                param_text = f"{label}: {value:.3f}"
                param_surf = self.font.render(param_text, True, text_color)
                self.control_surface.blit(param_surf, (x_pos, current_y))
                current_y += row_height

            # Current and Target values (Setpoint Key: S)
            if name == 'depth':
                current = self.physics.water_depth
                unit = "m"
            else:
                current = self.physics.orientation[['roll', 'pitch', 'yaw'].index(name)]
                unit = "°"

            current_text = f"Actual: {current:6.1f}{unit}"
            current_surf = self.font.render(current_text, True, TEXT_COLOR)
            self.control_surface.blit(current_surf, (x_pos, current_y))
            current_y += row_height

            setpoint_color = highlight_color if name == self.selected_controller and self.adjustment_mode == 'setpoint' else param_color
            target_text = f"Target (S): {self.setpoints[name]:.1f}{unit}"
            target_surf = self.font.render(target_text, True, setpoint_color)
            self.control_surface.blit(target_surf, (x_pos, current_y))


        # --- Draw PID outputs ---
        output_y_start = y_start + 180
        pid_output_title = self.font.render("PID Outputs (Ctrl to view P/I/D):", True, TEXT_COLOR)
        self.control_surface.blit(pid_output_title, (x_start, output_y_start))

        current_y = output_y_start + 25
        show_pid = pygame.key.get_pressed()[pygame.K_LCTRL]
        for i, name in enumerate(controllers):
            if not self.pid_enabled[name]: continue # Skip disabled controllers

            controller = self.pid_controllers[name]
            output = controller.P + controller.I + controller.D

            if show_pid:
                output_text = f"{name.capitalize()}: {output:6.2f} (P:{controller.P:5.2f} I:{controller.I:5.2f} D:{controller.D:5.2f})"
            else:
                 output_text = f"{name.capitalize()}: {output:6.2f}"

            output_surf = self.font.render(output_text, True, TEXT_COLOR)
            self.control_surface.blit(output_surf, (x_start + (i % 2) * 380, current_y + (i // 2) * row_height))


        # --- Draw controls help ---
        help_x_start = x_start + 10
        help_y_start = output_y_start + 85 # Below PID outputs
        help_col_width = 250

        help_title = self.font.render("Controls:", True, TEXT_COLOR)
        self.control_surface.blit(help_title, (help_x_start, help_y_start))

        help_items_col1 = [
            "1-4: Select Controller",
            "R/P/Y/D: Toggle PID",
            "K/I/B/F/S: Select Param",
            "Enter: Exit Adjust Mode",
            "↑/↓: Adjust Coarse",
            "←/→: Adjust Fine",
            "LShift+↑↓←→: Fine Adjust",
            "Space: Reset Sim",
        ]
        help_items_col2 = [
            "Q/A: Roll Torque +/-",
            "W/Z: Pitch Torque +/-", # Z for pitch down
            "E/X: Yaw Torque +/-",   # X for yaw right
            "C/V: Depth Force +/-",
            "T: Toggle Random Perturb",
            "F1-F3: Select Test Pattern",
            "F5: Run Test Pattern",
            "F6: Toggle IMU Mode",
            "F7: Record Data (30s)",
        ]

        current_y = help_y_start + 20
        help_font = pygame.font.SysFont('Arial', 14)
        for item in help_items_col1:
            help_text = help_font.render(item, True, (200, 200, 200))
            self.control_surface.blit(help_text, (help_x_start, current_y))
            current_y += 16

        current_y = help_y_start + 20
        for item in help_items_col2:
            help_text = help_font.render(item, True, (200, 200, 200))
            self.control_surface.blit(help_text, (help_x_start + help_col_width, current_y))
            current_y += 16

        # Show current adjustment mode
        mode_text = f"Adjusting: {self.adjustment_mode.upper()} for {self.selected_controller.capitalize()}"
        if self.adjustment_mode == 'none': mode_text = "Adjusting: None"
        mode_surf = self.font.render(mode_text, True, highlight_color)
        self.control_surface.blit(mode_surf, (help_x_start + help_col_width * 2 - 20, help_y_start))


    def render_telemetry(self):
        """Render telemetry information (Thrusters, Physics, Status)"""
        # Clear surface
        self.telemetry_surface.fill(PLOT_BG_COLOR)

        # Draw title
        title = "ROV Telemetry"
        title_surf = self.large_font.render(title, True, TEXT_COLOR)
        self.telemetry_surface.blit(title_surf, (10, 10))

        x_start = 20
        y_start = 50
        col_width = 180
        row_height = 20

        # --- Draw thruster values ---
        thruster_title = self.font.render("Thruster Outputs [-1, 1]:", True, TEXT_COLOR)
        self.telemetry_surface.blit(thruster_title, (x_start, y_start))

        thruster_names = [
            "P FL", "P FR", "P BR", "P BL", # Planar
            "V FL", "V FR", "V BL", "V BR"  # Vertical
        ]

        current_y = y_start + 25
        for i, (name, value) in enumerate(zip(thruster_names, self.thruster_values)):
            # Color based on value magnitude and sign
            mag = abs(value)
            if value > 0.01: color = (int(100 + 155 * mag), 255, int(100 + 155 * mag)) # Greenish positive
            elif value < -0.01: color = (255, int(100 + 155 * mag), int(100 + 155 * mag)) # Reddish negative
            else: color = (150, 150, 150) # Gray for near zero

            thruster_text = f"{name}: {value: .2f}" # Space for sign alignment
            thruster_surf = self.font.render(thruster_text, True, color)

            # Draw values in two columns
            col_idx = i // 4
            row_idx = i % 4
            self.telemetry_surface.blit(thruster_surf, (x_start + col_idx * col_width, current_y + row_idx * row_height))

        # --- Draw physics info ---
        physics_y_start = y_start + 120
        physics_title = self.font.render("Physics State:", True, TEXT_COLOR)
        self.telemetry_surface.blit(physics_title, (x_start, physics_y_start))

        current_y = physics_y_start + 25
        # Position
        pos_text = f"Pos (X,Y,Z): {self.physics.position[0]:5.1f}, {self.physics.position[1]:5.1f}, {self.physics.position[2]:5.1f} m"
        pos_surf = self.font.render(pos_text, True, TEXT_COLOR)
        self.telemetry_surface.blit(pos_surf, (x_start, current_y))
        current_y += row_height
        # Velocity
        vel_text = f"Vel (X,Y,Z): {self.physics.velocity[0]:5.1f}, {self.physics.velocity[1]:5.1f}, {self.physics.velocity[2]:5.1f} m/s"
        vel_surf = self.font.render(vel_text, True, TEXT_COLOR)
        self.telemetry_surface.blit(vel_surf, (x_start, current_y))
        current_y += row_height
        # Angular Velocity (degrees/s)
        ang_vel_deg = np.degrees(self.physics.angular_velocity)
        ang_vel_text = f"AngVel(R,P,Y):{ang_vel_deg[0]:5.1f}, {ang_vel_deg[1]:5.1f}, {ang_vel_deg[2]:5.1f} °/s"
        ang_vel_surf = self.font.render(ang_vel_text, True, TEXT_COLOR)
        self.telemetry_surface.blit(ang_vel_surf, (x_start, current_y))

        # --- Draw disturbance & test info ---
        status_y_start = physics_y_start + 100
        status_title = self.font.render("Status:", True, TEXT_COLOR)
        self.telemetry_surface.blit(status_title, (x_start, status_y_start))

        current_y = status_y_start + 25
        # Disturbances
        dist_text = f"Disturbance Torques (R,P,Y): {self.disturbance['roll_torque']:.1f}, {self.disturbance['pitch_torque']:.1f}, {self.disturbance['yaw_torque']:.1f} Nm"
        dist_surf = self.font.render(dist_text, True, TEXT_COLOR)
        self.telemetry_surface.blit(dist_surf, (x_start, current_y))
        current_y += row_height
        dist2_text = f"Disturbance Force (Z): {self.disturbance['vertical_force']:.1f} N"
        dist2_surf = self.font.render(dist2_text, True, TEXT_COLOR)
        self.telemetry_surface.blit(dist2_surf, (x_start, current_y))
        current_y += row_height
        # Perturbations
        pert_text = f"Random Perturb (T): {'ON' if self.perturbation_active else 'OFF'}"
        pert_surf = self.font.render(pert_text, True, (0, 255, 0) if self.perturbation_active else (255, 100, 100))
        self.telemetry_surface.blit(pert_surf, (x_start, current_y))
        current_y += row_height

        # Test Pattern Status
        test_mode_text = f"Test Pattern (F1-F3): {self.test_mode.capitalize()}"
        test_mode_surf = self.font.render(test_mode_text, True, TEXT_COLOR)
        self.telemetry_surface.blit(test_mode_surf, (x_start, current_y))
        current_y += row_height

        test_status_text = f"Test Status (F5): {'Running' if self.test_running else 'Stopped'}"
        test_status_color = (0, 255, 0) if self.test_running else (255, 100, 100)
        test_status_surf = self.font.render(test_status_text, True, test_status_color)
        self.telemetry_surface.blit(test_status_surf, (x_start, current_y))

        if self.test_running:
            test_time_text = f"Test Time: {self.sim_time:.1f}s"
            test_time_surf = self.font.render(test_time_text, True, TEXT_COLOR)
            self.telemetry_surface.blit(test_time_surf, (x_start + test_status_surf.get_width() + 10, current_y))
        current_y += row_height


        # --- Draw IMU status ---
        imu_y_start = status_y_start + 130
        imu_title = self.font.render("IMU Source (F6):", True, TEXT_COLOR)
        self.telemetry_surface.blit(imu_title, (x_start, imu_y_start))

        current_y = imu_y_start + 25
        imu_mode_text = f"Mode: {self.imu_mode.capitalize()}"
        imu_mode_color = (0, 255, 255) if self.imu_mode == 'hardware' else (150, 150, 255)
        imu_mode_surf = self.font.render(imu_mode_text, True, imu_mode_color)
        self.telemetry_surface.blit(imu_mode_surf, (x_start, current_y))
        current_y += row_height

        # Recording Status
        rec_status_text = f"Recording (F7): {'ACTIVE' if self.imu_recording else 'Idle'}"
        rec_color = (255, 50, 50) if self.imu_recording else (100, 255, 100)
        rec_surf = self.font.render(rec_status_text, True, rec_color)
        self.telemetry_surface.blit(rec_surf, (x_start, current_y))
        if self.imu_recording and self.record_filename:
             rec_file_text = os.path.basename(self.record_filename)
             rec_file_surf = self.font.render(rec_file_text, True, rec_color)
             self.telemetry_surface.blit(rec_file_surf, (x_start + rec_surf.get_width() + 5, current_y))


    def initialize_imu_provider(self, mode="simulated", bus=7, addr=BNO055_ADDRESS_A):
        """Initialize or switch the BNO055 data provider"""
        logger.info(f"Attempting to initialize IMU provider in '{mode}' mode...")
        # Stop existing provider if running
        if self.imu_provider:
            logger.info("Stopping existing IMU provider...")
            self.imu_provider.stop()
            self.imu_provider = None # Ensure it's cleared

        self.imu_mode = mode
        self.use_real_imu = False # Reset flag

        try:
            if mode == "hardware":
                if not bno055_available:
                    logger.error("Hardware mode requested, but BNO055 module is not available.")
                    raise ImportError("BNO055 module not found")

                # Pass bus and address if needed
                self.imu_provider = BNO055DataProvider(mode="hardware", bus_number=bus, address=addr)
                if self.imu_provider.mode != "hardware": # Check if fallback occurred
                     logger.warning("IMU provider failed to initialize in hardware mode, fell back to simulated.")
                     self.imu_mode = "simulated"
                else:
                     self.use_real_imu = True # Using real hardware data for state
                     logger.info("Successfully initialized BNO055 in hardware mode.")

            else: # mode == "simulated"
                self.imu_provider = BNO055DataProvider(mode="simulated")
                logger.info("Initialized IMU provider in simulated mode.")

            # Start the provider thread
            self.imu_provider.start()
            # Give the thread a moment to start up
            time.sleep(0.2)
            if not self.imu_provider.running:
                 logger.error("IMU provider thread failed to start.")
                 self.imu_provider = None
                 return False

            return True

        except Exception as e:
            logger.error(f"Failed to initialize IMU provider in '{mode}' mode: {e}")
            self.imu_provider = None
            self.imu_mode = "simulated" # Fallback to simulated on error
            # Try initializing in simulated mode as a fallback
            try:
                 logger.info("Attempting fallback to simulated mode...")
                 self.imu_provider = BNO055DataProvider(mode="simulated")
                 self.imu_provider.start()
                 time.sleep(0.1)
                 if self.imu_provider.running:
                     logger.info("Successfully initialized fallback simulated IMU provider.")
                     return True
                 else:
                     logger.error("Fallback simulated IMU provider also failed to start.")
                     return False
            except Exception as fallback_e:
                 logger.error(f"Error initializing fallback simulated provider: {fallback_e}")
                 return False


    def record_session_thread(self, filename, duration):
        """Wrapper function to run recording in a separate thread"""
        logger.info(f"Starting recording thread for {duration}s to {filename}")
        if not self.imu_provider:
            logger.error("Recording thread: IMU provider not initialized.")
            self.imu_recording = False
            return

        try:
            # Record data using the provider's method
            result = self.imu_provider.record_session(file_path=filename, duration=duration)
            if result:
                logger.info(f"Recording thread finished. Data saved to {result}")
            else:
                logger.error("Recording thread: Failed to save recording.")
        except Exception as e:
            logger.error(f"Recording thread encountered an error: {e}")
        finally:
            # Ensure recording flag is reset even if errors occur
            self.imu_recording = False
            self.record_filename = None # Clear filename after recording attempt


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='ROV PID Simulator using BNO055')
    parser.add_argument('--mode', choices=['hardware', 'simulated'], default='simulated',
                        help='IMU data source (hardware=real BNO055, simulated=generated data)')
    parser.add_argument('--bus', type=int, default=7, help='I2C bus number for BNO055 (default: 7)')
    parser.add_argument('--address', type=lambda x: int(x, 0), default=BNO055_ADDRESS_A,
                        help=f'I2C address for BNO055 (hex, e.g., 0x28, default: {BNO055_ADDRESS_A:#04x})')

    args = parser.parse_args()

    # Create simulator instance
    sim = PIDSimulator()

    # Initialize IMU provider based on arguments
    sim.initialize_imu_provider(mode=args.mode, bus=args.bus, addr=args.address)

    # Run the simulator
    try:
        sim.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down.")
    finally:
        # Ensure cleanup happens
        if sim.imu_provider:
            sim.imu_provider.stop()
        pygame.quit()

if __name__ == "__main__":
    main()