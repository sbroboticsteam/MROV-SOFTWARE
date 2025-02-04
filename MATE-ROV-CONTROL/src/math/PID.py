class PIDController():
    def __init__(self, p, i =0,d=0):
        self.dt = 1/60 # placeholder, should be a value that checks for time in between updates. may use 
        self.p = p
        self.i = i
        self.d = d

        self.sum = 0
        self.prev = 0
        pass

    def calculate(self, setpoint, measurement):
        """
        Calculates the PID output given the setpoint and system measurement
        Params:
            setpoint: the goal of the system
            measurement: the current sensor value for the system

        """
        error = setpoint - measurement

        derivative = (error - self.prev) / self.dt
        integral = self.sum + error * self.dt
        
        self.prev = error

        return self.p * measurement + self.i * integral + self.d * derivative

    def resetIntegrator(self):
        self.sum = 0