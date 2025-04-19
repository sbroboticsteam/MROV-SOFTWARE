from smbus2 import SMBus
from time import sleep
import socket
import json
import time
import select
# --- Add BNO055 Import ---
try:
    # Assuming bno055.py is accessible (e.g., in the same directory or Python path)
    from bno055 import BNO055, BNO055_ADDRESS_A
except ImportError:
    print("ERROR: Could not import BNO055 class. Make sure bno055.py is accessible.")
    BNO055 = None # Define as None if import fails
    
# PCA9685 constants
PCA9685_ADDRESS = 0x40
MODE1 = 0x00
PRESCALE = 0xFE
LED0_ON_L = 0x06


# --- PID Controller Class ---
class PID:
    def __init__(self, Kp, Ki, Kd, setpoint=0, sample_time=0.01, output_limits=(-1, 1)):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.setpoint = setpoint
        self.sample_time = sample_time
        self.output_limits = output_limits

        self._last_time = time.time()
        self._last_error = 0
        self._proportional = 0
        self._integral = 0
        self._derivative = 0

    def update(self, current_value):
        current_time = time.time()
        delta_time = current_time - self._last_time

        if delta_time < self.sample_time:
            return self._last_output # Return last output if sample time not elapsed

        error = self.setpoint - current_value
        delta_error = error - self._last_error

        self._proportional = self.Kp * error
        self._integral += self.Ki * error * delta_time
        # Clamp integral term
        if self.output_limits:
            min_out, max_out = self.output_limits
            self._integral = max(min(self._integral, max_out), min_out)

        self._derivative = 0
        if delta_time > 0:
            self._derivative = self.Kd * delta_error / delta_time

        output = self._proportional + self._integral + self._derivative

        # Clamp final output
        if self.output_limits:
            output = max(min(output, self.output_limits[1]), self.output_limits[0])

        self._last_error = error
        self._last_time = current_time
        self._last_output = output

        return output

    def reset(self):
        self._last_time = time.time()
        self._last_error = 0
        self._integral = 0
        self._derivative = 0
        self._last_output = 0

    def set_gains(self, Kp, Ki, Kd):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd

    def set_setpoint(self, setpoint):
        self.setpoint = setpoint
        self.reset() # Reset PID state when setpoint changes significantly


# --- PCA9685 Class ---
class PCA9685:
    def __init__(self, bus_number=7, address=PCA9685_ADDRESS):
        self.bus = SMBus(bus_number)
        self.address = address
        self.channels = [PCA9685Channel(self, i) for i in range(16)]
        self.reset()

    def reset(self):
        self.bus.write_byte_data(self.address, MODE1, 0x00)
        sleep(0.01)

    @property
    def frequency(self):
        return self._frequency

    @frequency.setter
    def frequency(self, freq_hz):
        self._frequency = freq_hz
        prescale_val = int(25000000.0 / (4096 * freq_hz)) - 1

        mode1 = self.bus.read_byte_data(self.address, MODE1)
        # Enter sleep mode
        self.bus.write_byte_data(self.address, MODE1, (mode1 & 0x7F) | 0x10)
        sleep(0.001)  # micro-delay
        self.bus.write_byte_data(self.address, PRESCALE, prescale_val)
        sleep(0.001)  # micro-delay
        # Exit sleep mode
        self.bus.write_byte_data(self.address, MODE1, mode1)
        sleep(0.005)
        # Restart
        self.bus.write_byte_data(self.address, MODE1, mode1 | 0x80)
        sleep(0.001)  # micro-delay

    def deinit(self):
        try:
            self.bus.close()
        except:
            pass

class PCA9685Channel:
    def __init__(self, pca, channel):
        self.pca = pca
        self.channel = channel
        self._duty_cycle = 0

    @property
    def duty_cycle(self):
        return self._duty_cycle

    @duty_cycle.setter
    def duty_cycle(self, value):
        self._duty_cycle = value
        on_value = 0
        off_value = value & 0xFFFF
        base_reg = LED0_ON_L + (4 * self.channel)

        # Write each register with a small delay
        self.pca.bus.write_byte_data(self.pca.address, base_reg, on_value & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 1, (on_value >> 8) & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 2, off_value & 0xFF)
        time.sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 3, (off_value >> 8) & 0xFF)
        time.sleep(0.001)

class ESC:
    def __init__(self, channel, pca):
        self.channel = channel
        self.pca = pca
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1100
        self.MAX_PULSE = 1900
        self.FORWARD_MIN = 1525
        self.REVERSE_MAX = 1475
        # Each ESC starts at the 1500µs neutral pulse
        self.current_pulse = self.STOP_PULSE

    def initialize(self):
        # Send neutral (1500µs) to let the ESC beep & detect
        self._set_pulse_width(self.STOP_PULSE)
        sleep(2)
        print(f"ESC on channel {self.channel} initialized")

    def set_state(self, state):
        # If state>0 => forward from 1525 to 1900;
        # if state<0 => reverse from 1475 down to 1100;
        # else => neutral 1500
        if state > 0:
            pulse_width = self.FORWARD_MIN + (state * (self.MAX_PULSE - self.FORWARD_MIN))
        elif state < 0:
            pulse_width = self.REVERSE_MAX - (abs(state) * (self.REVERSE_MAX - self.MIN_PULSE))
        else:
            pulse_width = self.STOP_PULSE

        if pulse_width == self.current_pulse:
            return  # No need to re-send if unchanged
        

        self.current_pulse = pulse_width
        self._set_pulse_width(pulse_width)

    def _set_pulse_width(self, pulse_width):
        offset = 9
        pulse_width += offset
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        print(f"Channel {self.channel}: pulse {pulse_width} µs -> duty_cycle {duty_cycle}")
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        # A tiny pause can help the PCA9685 register the new duty cycle
        time.sleep(0.001)

class ESCController:
    def __init__(self, esc_channels, pca):
        self.escs = [ESC(channel, pca) for channel in esc_channels]

    def initialize_all(self):
        print("Initializing all ESCs...")
        for esc in self.escs:
            esc.initialize()
        print("All ESCs initialized.")

    def set_all_states(self, states):
        if len(states) != len(self.escs):
            print(f"Expected {len(self.escs)} states, got {len(states)}")
            return
        for esc, state in zip(self.escs, states):
            esc.set_state(state)

    def stop_all(self):
        for esc in self.escs:
            esc.set_state(0)

    def sendCustomPeriod(self, period):
        # Send a custom period to all ESCs
        for esc in self.escs:
            esc._set_pulse_width(period)
            
# --- Motor Mixing Logic ---
# Define which motors control which axis based on your ROV build
# Indices correspond to esc_channels = [0, 7, 2, 5, 1, 4, 6, 3]
# Horizontal: 0(FL), 7(FR), 2(BL), 5(BR)
# Vertical:   1(FL_UP), 4(FR_UP), 6(BR_UP), 3(BL_UP)

# Example mixing - ADJUST THESE BASED ON YOUR ROV'S THRUSTER CONFIGURATION
def mix_motors(base_states, heading_adj, pitch_adj, roll_adj):
    final_states = list(base_states) # Start with joystick commands

    # --- Heading Adjustment (Yaw) ---
    # Affects horizontal thrusters for turning
    # Example: Positive adj turns right (increase left, decrease right)
    final_states[0] += heading_adj # FL Horizontal
    final_states[2] += heading_adj # BL Horizontal
    final_states[7] -= heading_adj # FR Horizontal
    final_states[5] -= heading_adj # BR Horizontal

    # --- Pitch Adjustment ---
    # Affects vertical thrusters (front vs back)
    # Example: Positive adj pitches up (increase front up, decrease back up)
    final_states[1] += pitch_adj # FL Vertical Up
    final_states[4] += pitch_adj # FR Vertical Up
    final_states[3] -= pitch_adj # BL Vertical Up
    final_states[6] -= pitch_adj # BR Vertical Up

    # --- Roll Adjustment ---
    # Affects vertical thrusters (left vs right)
    # Example: Positive adj rolls right (increase left up, decrease right up)
    final_states[1] += roll_adj # FL Vertical Up
    final_states[3] += roll_adj # BL Vertical Up
    final_states[4] -= roll_adj # FR Vertical Up
    final_states[6] -= roll_adj # BR Vertical Up

    # Clamp all final states between -1.0 and 1.0
    final_states = [max(min(state, 1.0), -1.0) for state in final_states]
    return final_states

def main():
    # --- Initialize BNO055 ---
    bno = None
    if BNO055:
        try:
            print("Initializing BNO055 sensor...")
            bno = BNO055(bus_number=7, address=BNO055_ADDRESS_A)
            if not bno.begin():
                print("WARNING: Failed to initialize BNO055! PID inactive.")
                bno = None
            else:
                print("BNO055 Initialized Successfully.")
                # Optional: Check initial calibration
                time.sleep(1) # Wait a bit after init
                cal_sys, cal_gyro, cal_accel, cal_mag = bno.get_calibration()
                print(f"Initial Calibration: Sys={cal_sys}, Gyro={cal_gyro}, Accel={cal_accel}, Mag={cal_mag}")
        except Exception as e:
            print(f"ERROR: Exception during BNO055 initialization: {e}")
            bno = None
    else:
        print("WARNING: BNO055 class not available. PID inactive.")

    # --- Initialize PID Controllers ---
    # !! THESE GAINS (Kp, Ki, Kd) NEED TUNING !!
    # Start with small P, I=0, D=0
    pid_heading = PID(Kp=0.05, Ki=0.0, Kd=0.01, setpoint=0, sample_time=0.05, output_limits=(-0.5, 0.5))
    pid_pitch = PID(Kp=0.08, Ki=0.0, Kd=0.02, setpoint=0, sample_time=0.05, output_limits=(-0.5, 0.5))
    pid_roll = PID(Kp=0.08, Ki=0.0, Kd=0.02, setpoint=0, sample_time=0.05, output_limits=(-0.5, 0.5))

    # Flag to enable/disable PID
    pid_enabled = True if bno else False # Only enable if BNO initialized
    target_heading = None # Will be set to current heading initially

    # --- Initialize PCA9685 and ESCs ---
    esc_channels = [0, 7, 2, 5, 1, 4, 6, 3]
    pca = PCA9685(bus_number=7)
    pca.frequency = 50
    esc_controller = ESCController(esc_channels, pca)
    esc_controller.initialize_all()

    # ... existing socket setup ...
    HOST = '192.168.1.237' # Make sure this is the Pi's IP
    PORT = 4891
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"Server listening on {HOST}:{PORT}...")

    last_print_time = time.time()

    try:
        while True:
            print("Waiting for a client connection...")
            com_socket, addy = server.accept()
            print(f"Connected to {addy}")
            client_connected = True
            last_command_time = time.time()
            
            pid_enabled = True if bno else False # Reset enable state based on BNO status
            target_heading = None # Reset target heading
            pid_heading.reset()
            pid_pitch.reset()
            pid_roll.reset()
            print(f"Initial PID state on connect: {'Enabled' if pid_enabled else 'Disabled'}")
            
            while client_connected:
                # Set a timeout for recv
                ready_to_read, _, _ = select.select([com_socket], [], [], 0.1) # 100ms timeout

                base_motor_states = [0.0] * 8 # Default to zero if no command received

                if ready_to_read:
                    try:
                        data = com_socket.recv(1024)
                        if not data:
                            print("Client disconnected.")
                            client_connected = False
                            break # Exit inner loop

                        motor_values_str = data.decode('utf-8')
                        # Handle potential multiple JSON objects concatenated
                        # Find the last valid JSON object
                        last_brace = motor_values_str.rfind('}')
                        if last_brace != -1:
                            first_brace = motor_values_str.rfind('{', 0, last_brace)
                            if first_brace != -1:
                                valid_json_str = motor_values_str[first_brace : last_brace + 1]
                                try:
                                    motor_values_dict = json.loads(valid_json_str)
                                    base_motor_states = motor_values_dict.get('motor_values', [0.0] * 8)
                                    if not isinstance(base_motor_states, list) or len(base_motor_states) != 8:
                                        print("Invalid motor values format received. Using zeros.")
                                        base_motor_states = [0.0] * 8
                                    last_command_time = time.time() # Update time of last valid command
                                except (json.JSONDecodeError, KeyError) as e:
                                    print(f"Error parsing motor values: {e} - JSON: '{valid_json_str}'")
                                    base_motor_states = [0.0] * 8 # Use zeros on error
                            else:
                                base_motor_states = [0.0] * 8 # Use zeros if no opening brace found
                        else:
                             base_motor_states = [0.0] * 8 # Use zeros if no closing brace found

                    except socket.error as e:
                        print(f"Socket error: {e}")
                        client_connected = False
                        break
                else:
                    # Timeout occurred - check if connection is stale
                    if time.time() - last_command_time > 5.0: # 5 second timeout
                         print("Client connection timed out (no commands received).")
                         client_connected = False
                         break # Exit inner loop

                # --- PID Calculation and Motor Mixing ---
                final_motor_states = base_motor_states
                current_heading, current_roll, current_pitch = 0, 0, 0 # Defaults if BNO fails

                if pid_enabled and bno:
                    try:
                        # Read current orientation
                        current_heading, current_roll, current_pitch = bno.get_euler()
                        # Handle heading wrap-around (0-360 degrees) - important for PID
                        # If target_heading is None, set it to the current heading
                        if target_heading is None:
                            target_heading = current_heading
                            pid_heading.set_setpoint(target_heading)
                            print(f"Initial Target Heading set to: {target_heading:.2f}")

                        # Calculate heading error considering wrap-around
                        heading_error = target_heading - current_heading
                        if heading_error > 180:
                            heading_error -= 360
                        elif heading_error < -180:
                            heading_error += 360

                        # Update PIDs (use wrapped heading error for heading PID)
                        # Note: We directly use the error here, assuming PID class uses setpoint - current_value
                        # If PID class calculates error internally, adjust accordingly.
                        # Let's modify the PID update slightly for heading:
                        heading_adj = pid_heading.update(current_heading) # PID calculates error internally now
                        pitch_adj = pid_pitch.update(current_pitch) # Target pitch is 0
                        roll_adj = pid_roll.update(current_roll)   # Target roll is 0

                        # Mix PID adjustments with base commands
                        final_motor_states = mix_motors(base_motor_states, heading_adj, pitch_adj, roll_adj)

                        # Print status periodically
                        current_time = time.time()
                        if current_time - last_print_time >= 1.0: # Print every second
                            print(f"H:{current_heading:6.1f} P:{current_pitch:6.1f} R:{current_roll:6.1f} | "
                                  f"TgtH:{target_heading:6.1f} | "
                                  f"Adj H:{heading_adj:5.2f} P:{pitch_adj:5.2f} R:{roll_adj:5.2f}")
                            print(f"Base States: {[f'{s:5.2f}' for s in base_motor_states]}")
                            print(f"Final States:{[f'{s:5.2f}' for s in final_motor_states]}")
                            last_print_time = current_time

                    except IOError as e:
                        print(f"IOError reading BNO055: {e}. Disabling PID.")
                        pid_enabled = False
                        final_motor_states = base_motor_states # Revert to base states
                    except Exception as e:
                         print(f"Unexpected error during PID/BNO read: {e}")
                         # Decide if PID should be disabled or just skip this cycle
                         final_motor_states = base_motor_states

                # --- Update ESCs ---
                esc_controller.set_all_states(final_motor_states)

                # Small delay to prevent busy-waiting
                # time.sleep(0.01) # Already handled by select timeout and BNO read time

            # --- Client Disconnected ---
            print(f"Connection with {addy} ended.")
            # Stop motors when client disconnects
            esc_controller.stop_all()
            print("Motors stopped due to client disconnect.")
            # Reset target heading for next connection
            target_heading = None
            pid_heading.reset()
            pid_pitch.reset()
            pid_roll.reset()
            com_socket.close()

    except KeyboardInterrupt:
        print("Server is shutting down...")
    finally:
        # Ensure the motors are stopped and resources released
        print("Stopping all motors...")
        esc_controller.stop_all()
        print("Deinitializing PCA9685...")
        pca.deinit()
        if bno:
            print("Closing BNO055 connection...")
            try:
                bno.close()
            except Exception as e:
                print(f"Error closing BNO055: {e}")
        if 'server' in locals() and server:
             print("Closing server socket...")
             server.close()
        print("Server closed.")


if __name__ == '__main__':
    main()