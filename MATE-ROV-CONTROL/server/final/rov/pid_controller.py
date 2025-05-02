import time
import math
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

    def reset(self):
        self.previous_error = 0.0
        self.integral = 0.0
        self.runtime.reset()
