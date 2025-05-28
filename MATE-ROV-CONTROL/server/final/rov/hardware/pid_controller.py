import time
import sys
import numpy as np
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

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
        self.a = 0.0

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
        self.name = "PID"

        # Support constructor overloads
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
            
    def set_name(self, name):
        """Set a name for this PID controller for identification in logs"""
        self.name = name
        return self

    def PID_Power(self, curr_pos, target_pos):
        self.error = target_pos - curr_pos
        self.error_change = self.error - self.previous_error

        self.P = self.kp * self.error

        self.delta_time = self.runtime.seconds()
        self.runtime.reset()

        self.area += ((self.error + self.previous_error) * self.delta_time) / 2

        if abs(self.error) < self.tolerance:
            self.area = 0.0
        if target_pos != self.previous_target:
            self.area = 0.0

        self.I = self.area * self.ki

        self.current_filter_estimate = ((1 - self.a) * self.error_change +
                                        self.a * self.previous_filter_estimate)

        self.D = self.kd * (self.current_filter_estimate / self.delta_time)
        
         # Log PID components at DEBUG level
        logger.debug(f"PID {self.name}: Target={target_pos:.2f}, Current={curr_pos:.2f}, Error={self.error:.2f}")
        logger.debug(f"PID {self.name}: P={self.P:.4f} (kp={self.kp}), I={self.I:.4f}, D={self.D:.4f}, Output={self.P + self.I + self.D:.4f}")

        self.previous_error = self.error
        self.previous_filter_estimate = self.current_filter_estimate
        self.previous_target = target_pos

        return self.P + self.I + self.D

    def reset(self):
        self.previous_error = 0.0
        self.area = 0.0  # Change from self.integral
        self.runtime.reset()

# --------------------------- Chassis Control Class ---------------------------
class ChassisControl:
    def __init__(self):
        # Initialize target values
        self.x_target = 0
        self.y_target = 0
        self.z_target = 0
        self.yaw_target = 0
        self.pitch_target = 0
        self.roll_target = 0


        # Use named PID controllers for better logging
        self.pidX = PID_Controller(0, 0, 0, 0).set_name("X")
        self.pidY = PID_Controller(0, 0, 0, 0).set_name("Y")
        self.pidZ = PID_Controller(0, 0, 0, 0).set_name("Z")
        self.pidRoll = PID_Controller(0.09, 0, 0, 0).set_name("Roll")
        self.pidPitch = PID_Controller(0.15, 0, 0, 0).set_name ("Pitch")
        self.pidYaw = PID_Controller(0, 0, 0, 0).set_name("Yaw")
        
    def updateTarget(self, imuData, x, y, rx, ry, rT, lT):
        logger.debug(f"BEFORE Target Update - Yaw: {self.yaw_target:.2f}°, Roll: {self.roll_target:.2f}°, Pitch: {self.pitch_target:.2f}°")
        e = sys.float_info.epsilon
        if abs(x) > e :
            self.x_target = imuData[0]
            logger.info(f"*** X target UPDATED to {self.x_target:.2f} ***")
        if abs(y) > e :
            self.y_target = imuData[1]
            logger.info(f"*** Y target UPDATED to {self.y_target:.2f} ***")
        if abs(rx) > e :
            self.yaw_target = imuData[5]
            logger.info(f"*** Yaw target UPDATED to {self.yaw_target:.2f}° (input: {rx:.2f}) ***")
        if abs(ry) >  e :
            self.pitch_target = imuData[4]
            logger.info(f"*** PITCH target UPDATED to {self.pitch_target:.2f}° (input: {ry:.2f}) ***")
        if abs(rT) > e  or abs(lT) > e  :
            self.z_target = imuData[2]
            logger.info(f"*** Z target UPDATED to {self.z_target:.2f} ***")
        
        logger.debug(f"AFTER Target Update - Yaw: {self.yaw_target:.2f}°, Roll: {self.roll_target:.2f}°, Pitch: {self.pitch_target:.2f}°")

    def arcadeDrive6(self, input_vector):
        """
        Advanced arcade drive with 6 degrees of freedom.
        input_vector: [x, y, z, roll, pitch, yaw]
        """
        # Inverse Kinematics for Planar Thrusters (X-Y movement and rotation)
        planar_front_left = -input_vector[1] +input_vector[0] + input_vector[5]
        planar_front_right = -input_vector[1] -input_vector[0] - input_vector[5]
        planar_back_right = input_vector[1] -input_vector[0] + input_vector[5]
        planar_back_left = input_vector[1] +input_vector[0] - input_vector[5]

        # Inverse Kinematics for Vertical Thrusters (Depth and Roll-Pitch Corrections)
        vertical_front_left = -input_vector[2] + input_vector[3] + input_vector[4]
        vertical_front_right = -input_vector[2] - input_vector[3] + input_vector[4]
        vertical_back_right = -input_vector[2] - input_vector[3] - input_vector[4]
        vertical_back_left = -input_vector[2] + input_vector[3] - input_vector[4]

        # Normalize Planar and Vertical Thruster Values
        planar_thrusters = self._normalize_thrusters([-planar_front_left, -planar_front_right, -planar_back_left, -planar_back_right])
        vertical_thrusters = self._normalize_thrusters([-vertical_front_left, -vertical_front_right, -vertical_back_right, -vertical_back_left])

        # Return motor power values for all thrusters
        return planar_thrusters + vertical_thrusters
    
    def _normalize_thrusters(self, thrusters):
        """Normalize thruster values if any exceed limits."""
        max_val = max(abs(t) for t in thrusters)
        if max_val > 1.0:
            thrusters = [t / max_val for t in thrusters]
        return thrusters
    
    def addVectors(self, vec1, vec2):
        """Add two vectors element-wise."""
        return [x + y for x, y in zip(vec1, vec2)]
    
    def controllerInput(self, x, y, rx, ry, rT, lT):
        """Convert raw controller inputs to a 6-axis control vector."""
        vert = rT - lT
        data = [x, y, vert, 0, ry, rx]  # [x, y, z, roll, pitch, yaw]
        return data
    
    def rotateVectors(self, power):
        """
        Rotate power vectors according to current orientation.
        This converts body-relative commands to world-relative commands.
        """
        roll_rad = np.radians(power[3])
        pitch_rad = np.radians(power[4])
        yaw_rad = np.radians(power[5])
        
        x_rotated = (power[0] * (np.cos(yaw_rad) * np.cos(pitch_rad)) +
                    power[1] * (np.cos(yaw_rad) * np.sin(pitch_rad) * np.sin(roll_rad) - np.sin(yaw_rad) * np.cos(roll_rad)) +
                    power[2] * (np.cos(yaw_rad) * np.sin(pitch_rad) * np.cos(roll_rad) + np.sin(yaw_rad) * np.sin(roll_rad)))

        y_rotated = (power[0] * (np.sin(yaw_rad) * np.cos(pitch_rad)) +
                    power[1] * (np.sin(yaw_rad) * np.sin(pitch_rad) * np.sin(roll_rad) + np.cos(yaw_rad) * np.cos(roll_rad)) +
                    power[2] * (np.sin(yaw_rad) * np.sin(pitch_rad) * np.cos(roll_rad) - np.cos(yaw_rad) * np.sin(roll_rad)))

        z_rotated = (-power[0] * np.sin(pitch_rad) +
                    power[1] * (np.cos(pitch_rad) * np.sin(roll_rad)) +
                    power[2] * (np.cos(pitch_rad) * np.cos(roll_rad)))
        
        return [x_rotated, y_rotated, z_rotated, power[3], power[4], power[5]]
    
    def PIDcorrection(self, imuData):
        """
        Calculate PID corrections based on IMU data.
        imuData: [x, y, z, roll, pitch, yaw] from IMU sensor
        """
        # Calculate power adjustments for each axis
        powerX = self.pidX.PID_Power(imuData[0], self.x_target)
        powerY = self.pidY.PID_Power(imuData[1], self.y_target)
        powerZ = self.pidZ.PID_Power(imuData[2], self.z_target)
        
        # For stability, try to keep roll and pitch at 0
        powerRoll = self.pidRoll.PID_Power(imuData[3], self.roll_target)  # Always target level
        powerPitch = -self.pidPitch.PID_Power(imuData[4], self.pitch_target) 
        
        # Yaw needs to match the target heading
        powerYaw = self.pidYaw.PID_Power(imuData[5], self.yaw_target)
        
        power = [powerX, powerY, powerZ, powerRoll, powerPitch, powerYaw]
        rotated = self.rotateVectors(power)
        return rotated
