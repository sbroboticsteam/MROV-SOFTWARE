import numpy as np
import time
import sys


# def arcadeDrive(x,y) -> list[float]: #og karamat code
#     """
#     turns stick axes into appropriate motor values
#     - the motor values are returned as an array of floats (details on the order below)
#     """
#     print(f"X: {x}")
#     print(f"Y: {y}")
#     maximum = max(abs(x), abs(y))
#     total, difference = x + y, x - y
#     out = []
#     # set speed according to the quadrant that the values are in
#     if x >= 0:
#         if y >= 0:  # I quadrant
#             out = [maximum, difference, difference, maximum]
#         else:       # II quadrant
#             out = [total, maximum, maximum, total]
#     else:
#         if y >= 0: # IV quadrant
#             out = [total, -maximum, -maximum, total]
#         else:      # III quadrant
#             out = [-maximum, difference, difference, -maximum]
#     print(out)
#     return out
#     """
#     robot motors:
#     - h is the heading / direction of the robot
#      _______
#     |4     1|
#     |  h->  |
#     |3_____2|

#     """
    
# def arcadeDrive2(x,y) -> list[int]: #ruthvick code to test?
#     maximum = max(abs(x), abs(y))
#     total,difference = x+y, x-y
#     out = []
#     # set speed according to the quadrant that the values are in
#     if x >= 0:
#         if y >= 0:  # I quadrant
#             out = [1,1 if difference > 0 else -1,1 if difference > 0 else -1,1]
#         else:       # II quadrant
#             out = [1 if total > 0 else -1, 1, 1, 1 if total > 0 else -1]
#     else:
#         if y >= 0: # IV quadrant
#             out = [1 if total > 0 else -1, 1, -1, 1 if total > 0 else -1]
#         else:      # III quadrant
#             out = [-1,1 if difference > 0 else -1,1 if difference > 0 else -1,-1]
#     return out
    
# def arcadeDrive3(x,y, rx, rT, lT) -> list[int]: #for strafing right left forward back turning
#     # print(f"X: {x}")
#     # print(f"Y: {y}")
#     # print(f"RX: {rx}")
    
#     PWM = rT - lT

#     frontLeft = y + x + rx #2
#     frontRight = y - x - rx #3
#     backRight = -y - x + rx #4  
#     backLeft = -y + x - rx #1
#     data = [-frontLeft,-frontRight,-backLeft,-backRight]
    
#     for val in data:
#         absVal = abs(val)
#         if absVal > 1.0:
#             data = [x/absVal for x in data]
            
#         # maxVal = max(abs(x) for x in data)
#         # if maxVal > 1.0:
#         #     data = [x / maxVal for x in data]

#     data.append(-PWM)
#     data.append(-PWM)
#     data.append(-PWM)
#     data.append(-PWM)
            
#     # print(data)
#     return data


def arcadeDrive6(input):
    ### Add Vectors is called before this in big control loop on jetson and is then output is parameter of this function
    
    # Inverse Kinematics for Planar Thrusters (X-Y movement and rotation)
    planar_front_left = -input[0] - input[1] - input[5]
    planar_front_right = -input[0] + input[1] + input[5]
    planar_back_right = +input[0] + input[1] - input[5]
    planar_back_left = +input[0] - input[1] + input[5]
    
    # planar_front_left = -input[0] - input[1] - input[5]
    # planar_front_right = -input[0] + input[1] + input[5]
    # planar_back_right = +input[0] + input[1] - input[5]
    # planar_back_left = +input[0] - input[1] + input[5]

    # Inverse Kinematics for Vertical Thrusters (Depth and Roll-Pitch Corrections)
    vertical_front_left = -input[2] - input[3] - input[4]
    vertical_front_right = -input[2] + input[3] - input[4]
    vertical_back_left = -input[2] - input[3] + input[4]
    vertical_back_right = -input[2] + input[3] + input[4]
    
    # vertical_front_left = input[2] + input[3] + input[4]
    # vertical_front_right = input[2] - input[3] + input[4]
    # vertical_back_left = input[2] + input[3] - input[4]
    # vertical_back_right = input[2] - input[3] - input[4]

    # Scaling and Normalization
    def normalize_thrusters(thrusters):
        max_val = max(abs(t) for t in thrusters)
        if max_val > 1.0:
            thrusters = [t / max_val for t in thrusters]
        return thrusters

    # Normalize Planar and Vertical Thruster Values
    planar_thrusters = normalize_thrusters([planar_front_left, planar_front_right, planar_back_right, planar_back_left])
    vertical_thrusters = normalize_thrusters([vertical_front_left, vertical_front_right, vertical_back_left, vertical_back_right])

    # Return motor power values for all thrusters
    return planar_thrusters + vertical_thrusters
    

def addVectors(controller, pid):
    new = []
    for x, y in zip(controller, pid):
        new.append(x + y)
    return new


# FNC CALLED FOR CTR (AKA ARCADE DRIVE 3)
# PID CORRECTION FNC
# NEW ARCARDE DRIVE 3.5 (A)
def controllerinput(x,y, rx, rT, lT):
    PWM = rT- lT
    data = [x, y, PWM, 0, 0, rx]
    
    return data


#??????
def rotateVectors(power):
    
    x_rotated = (power[0] * (np.cos(power[5]) * np.cos(power[4])) +
                 power[1] * (np.cos(power[5]) * np.sin(power[4]) * np.sin(power[3]) - np.sin(power[5]) * np.cos(power[3])) +
                 power[2] * (np.cos(power[5]) * np.sin(power[4]) * np.cos(power[3]) + np.sin(power[5]) * np.sin(power[3])))

    y_rotated = (power[0] * (np.sin(power[5]) * np.cos(power[4])) +
                 power[1] * (np.sin(power[5]) * np.sin(power[4]) * np.sin(power[3]) + np.cos(power[5]) * np.cos(power[3])) +
                 power[2] * (np.sin(power[5]) * np.sin(power[4]) * np.cos(power[3]) - np.cos(power[5]) * np.sin(power[3])))

    z_rotated = (-power[0] * np.sin(power[4]) +
                 power[1] * (np.cos(power[4]) * np.sin(power[3])) +
                 power[2] * (np.cos(power[4]) * np.cos(power[3])))
    
    return [x_rotated, y_rotated, z_rotated, power[3], power[4], power[5]]

def updateTarget(imuData, x,y, rx, rT, lT):
    e = sys.float_info.epsilon
    if x > 0 + e :
        x_target = imuData[0]
    if y > 0 + e :
        y_target = imuData[1]
    if rx > 0 + e :
        yaw_target = imuData[5]
    if rT > 0 + e or lT > 0 + e :
        z_target = imuData[3]

def PIDcorrection(imuData, x_target, y_target, z_target, yaw_target): #array i hope
    pidX = PID_Controller(0, 0, 0, 0)
    pidY = PID_Controller(0, 0, 0, 0)
    pidZ = PID_Controller(0, 0, 0, 0)
    pidRoll = PID_Controller(0, 0, 0, 0)
    pidPitch = PID_Controller(0, 0, 0, 0)
    pidYaw = PID_Controller(0, 0, 0, 0)
    
    curr_pos = imuData ## IMU SHIT
    powerX = pidX.PID_Power(curr_pos[0], x_target)
    powerY = pidY.PID_Power(curr_pos[1], y_target)
    powerZ = pidZ.PID_Power(curr_pos[2], z_target)
    powerYaw = pidYaw.PID_Power(curr_pos[5], yaw_target)
    
    
    powerRoll = pidRoll.PID_Power(curr_pos[3], 0)
    powerPitch = pidPitch.PID_Power(curr_pos[4], 0)
    
    power = [powerX, powerY, powerZ, powerRoll, powerPitch, powerYaw]

    return rotateVectors(power)
    

    """  Stuff to put in jetson while loop
    
    //global variables
    x_target, y_target, z_target, yaw_target
    
    while true:
        updateTarget(imuData, x,y, rx, rT, lT)
        PIDcorr = PIDcorrection(imuData, x_target, y_target, z_target, yaw_target)
        
        controller = controllerinput(x,y, rx, rT, lT)
        
        vectorret = addVectors(controller, pidcorr)
        
        motorval = arcadeDrive6(vectorret)
        
        MOTOR STUFF TO PWM
    
    """

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

        self.area += ((self.error + self.previous_error) * self.delta_time) / 2

        if abs(self.error) < self.tolerance:
            self.area = 0.0
        if target_pos != self.previous_target:
            self.area = 0.0

        self.I = self.area * self.ki

        self.current_filter_estimate = ((1 - self.a) * self.error_change +
                                        self.a * self.previous_filter_estimate)

        self.D = self.kd * (self.current_filter_estimate / self.delta_time)

        self.previous_error = self.error
        self.previous_filter_estimate = self.current_filter_estimate
        self.previous_target = target_pos

        return self.P + self.I + self.D



# def arcadeDrive4(controller_input, pid_input) -> list[float]:
#     """
#     Converts controller and PID inputs into motor power values for an ROV with 8 thrusters
#     (4 planar thrusters for X-Y movement, 4 vertical thrusters for depth control).
#     """
    
#     def get_roll():
#         return 0  # Placeholder for actual sensor data
    
#     def get_pitch():
#         return 0  # Placeholder for actual sensor data
    
#     def get_yaw():
#         return 0  # Placeholder for actual sensor data

#     # 3D Rotation matrix to convert global PID velocity vector into the local ROV reference frame
#     roll, pitch, yaw = -get_roll(), -get_pitch(), -get_yaw()

#     # Rotation matrix calculations
#     x_rotated = (pid_input[0] * (np.cos(yaw) * np.cos(pitch)) +
#                  pid_input[1] * (np.cos(yaw) * np.sin(pitch) * np.sin(roll) - np.sin(yaw) * np.cos(roll)) +
#                  pid_input[2] * (np.cos(yaw) * np.sin(pitch) * np.cos(roll) + np.sin(yaw) * np.sin(roll)))

#     y_rotated = (pid_input[0] * (np.sin(yaw) * np.cos(pitch)) +
#                  pid_input[1] * (np.sin(yaw) * np.sin(pitch) * np.sin(roll) + np.cos(yaw) * np.cos(roll)) +
#                  pid_input[2] * (np.sin(yaw) * np.sin(pitch) * np.cos(roll) - np.cos(yaw) * np.sin(roll)))

#     z_rotated = (-pid_input[0] * np.sin(pitch) +
#                  pid_input[1] * (np.cos(pitch) * np.sin(roll)) +
#                  pid_input[2] * (np.cos(pitch) * np.cos(roll)))

#     # Combine Controller Input with PID Correction
#     combined_x = controller_input[0] + x_rotated
#     combined_y = controller_input[1] + y_rotated
#     combined_z = controller_input[2] + z_rotated
#     combined_yaw = controller_input[5] + pid_input[5]

#     # Inverse Kinematics for Planar Thrusters (X-Y movement and rotation)
#     planar_front_left = combined_x + combined_y + combined_yaw
#     planar_front_right = combined_x - combined_y - combined_yaw
#     planar_back_right = -combined_x - combined_y + combined_yaw
#     planar_back_left = -combined_x + combined_y - combined_yaw

#     # Inverse Kinematics for Vertical Thrusters (Depth and Roll-Pitch Corrections)
#     vertical_front_left = combined_z + pid_input[3] + pid_input[4]
#     vertical_front_right = combined_z - pid_input[3] + pid_input[4]
#     vertical_back_left = combined_z + pid_input[3] - pid_input[4]
#     vertical_back_right = combined_z - pid_input[3] - pid_input[4]

#     # Scaling and Normalization
#     def normalize_thrusters(thrusters):
#         max_val = max(abs(t) for t in thrusters)
#         if max_val > 1.0:
#             thrusters = [t / max_val for t in thrusters]
#         return thrusters

#     # Normalize Planar and Vertical Thruster Values
#     planar_thrusters = normalize_thrusters([planar_front_left, planar_front_right, planar_back_right, planar_back_left])
#     vertical_thrusters = normalize_thrusters([vertical_front_left, vertical_front_right, vertical_back_left, vertical_back_right])

#     # Return motor power values for all thrusters
#     return planar_thrusters + vertical_thrusters

