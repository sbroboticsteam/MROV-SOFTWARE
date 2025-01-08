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
    
    PWM = rT- lT

    frontLeft = y + x + rx #2
    frontRight = y - x - rx #3
    backRight = -y - x + rx #4  
    backLeft = -y + x - rx #1
    data = [frontLeft,frontRight,backRight,backLeft]
    
    for val in data:
        absVal = abs(val)
        if absVal > 1.0:
            data = [x/absVal for x in data]
    
    data.append(PWM)
    data.append(PWM)
    data.append(PWM)
    data.append(PWM)
            
    # print(data)
    return data