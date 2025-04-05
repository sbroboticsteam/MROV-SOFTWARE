import numpy as np

def arcadeDrive(x,y) -> list[float]: #og karamat code
    """
    turns stick axes into appropriate motor values
    - the motor values are returned as an array of floats (details on the order below)
    """
    print(f"X: {x}")
    print(f"Y: {y}")
    maximum = max(abs(x), abs(y))
    total, difference = x + y, x - y
    out = []
    # set speed according to the quadrant that the values are in
    if x >= 0:
        if y >= 0:  # I quadrant
            out = [maximum, difference, difference, maximum]
        else:       # II quadrant
            out = [total, maximum, maximum, total]
    else:
        if y >= 0: # IV quadrant
            out = [total, -maximum, -maximum, total]
        else:      # III quadrant
            out = [-maximum, difference, difference, -maximum]
    print(out)
    return out
    """
    robot motors:
    - h is the heading / direction of the robot
     _______
    |4     1|
    |  h->  |
    |3_____2|

    """
    
def arcadeDrive2(x,y) -> list[int]: #ruthvick code to test?
    maximum = max(abs(x), abs(y))
    total,difference = x+y, x-y
    out = []
    # set speed according to the quadrant that the values are in
    if x >= 0:
        if y >= 0:  # I quadrant
            out = [1,1 if difference > 0 else -1,1 if difference > 0 else -1,1]
        else:       # II quadrant
            out = [1 if total > 0 else -1, 1, 1, 1 if total > 0 else -1]
    else:
        if y >= 0: # IV quadrant
            out = [1 if total > 0 else -1, 1, -1, 1 if total > 0 else -1]
        else:      # III quadrant
            out = [-1,1 if difference > 0 else -1,1 if difference > 0 else -1,-1]
    return out
    
def arcadeDrive3(x,y, rx, rT, lT) -> list[int]: #for strafing right left forward back turning
    # print(f"X: {x}")
    # print(f"Y: {y}")
    # print(f"RX: {rx}")
    
    PWM = rT - lT

    frontLeft = y + x + rx #2
    frontRight = y - x - rx #3
    backRight = -y - x + rx #4  
    backLeft = -y + x - rx #1
    data = [-frontLeft,-frontRight,-backLeft,-backRight]
    
    for val in data:
        absVal = abs(val)
        if absVal > 1.0:
            data = [x/absVal for x in data]
            
        # maxVal = max(abs(x) for x in data)
        # if maxVal > 1.0:
        #     data = [x / maxVal for x in data]

    data.append(-PWM)
    data.append(-PWM)
    data.append(-PWM)
    data.append(-PWM)
            
    # print(data)
    return data

def arcadeDrive4(controller_input, pid_input) -> list[float]:
    """
    Converts controller and PID inputs into motor power values for an ROV with 8 thrusters
    (4 planar thrusters for X-Y movement, 4 vertical thrusters for depth control).
    """
    
    def get_roll():
        return 0  # Placeholder for actual sensor data
    
    def get_pitch():
        return 0  # Placeholder for actual sensor data
    
    def get_yaw():
        return 0  # Placeholder for actual sensor data

    # 3D Rotation matrix to convert global PID velocity vector into the local ROV reference frame
    roll, pitch, yaw = -get_roll(), -get_pitch(), -get_yaw()

    # Rotation matrix calculations
    x_rotated = (pid_input[0] * (np.cos(yaw) * np.cos(pitch)) +
                 pid_input[1] * (np.cos(yaw) * np.sin(pitch) * np.sin(roll) - np.sin(yaw) * np.cos(roll)) +
                 pid_input[2] * (np.cos(yaw) * np.sin(pitch) * np.cos(roll) + np.sin(yaw) * np.sin(roll)))

    y_rotated = (pid_input[0] * (np.sin(yaw) * np.cos(pitch)) +
                 pid_input[1] * (np.sin(yaw) * np.sin(pitch) * np.sin(roll) + np.cos(yaw) * np.cos(roll)) +
                 pid_input[2] * (np.sin(yaw) * np.sin(pitch) * np.cos(roll) - np.cos(yaw) * np.sin(roll)))

    z_rotated = (-pid_input[0] * np.sin(pitch) +
                 pid_input[1] * (np.cos(pitch) * np.sin(roll)) +
                 pid_input[2] * (np.cos(pitch) * np.cos(roll)))

    # Combine Controller Input with PID Correction
    combined_x = controller_input[0] + x_rotated
    combined_y = controller_input[1] + y_rotated
    combined_z = controller_input[2] + z_rotated
    combined_yaw = controller_input[5] + pid_input[5]

    # Inverse Kinematics for Planar Thrusters (X-Y movement and rotation)
    planar_front_left = combined_x + combined_y + combined_yaw
    planar_front_right = combined_x - combined_y - combined_yaw
    planar_back_right = -combined_x - combined_y + combined_yaw
    planar_back_left = -combined_x + combined_y - combined_yaw

    # Inverse Kinematics for Vertical Thrusters (Depth and Roll-Pitch Corrections)
    vertical_front_left = combined_z + pid_input[3] + pid_input[4]
    vertical_front_right = combined_z - pid_input[3] + pid_input[4]
    vertical_back_left = combined_z + pid_input[3] - pid_input[4]
    vertical_back_right = combined_z - pid_input[3] - pid_input[4]

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

