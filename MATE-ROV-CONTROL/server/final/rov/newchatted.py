import logging
import time
import argparse
import json
from smbus2 import SMBus
from time import sleep

from hardware.controller import ControllerMapper
from hardware.servo import Arm, ArmState
from hardware.ethernet_man import EthernetManager

# --------------------------- Logging Setup ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

# --------------------------- PCA9685 & ESC Classes ---------------------------
PCA9685_ADDRESS = 0x40
MODE1 = 0x00
PRESCALE = 0xFE
LED0_ON_L = 0x06

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
        self.bus.write_byte_data(self.address, MODE1, (mode1 & 0x7F) | 0x10)
        sleep(0.001)
        self.bus.write_byte_data(self.address, PRESCALE, prescale_val)
        sleep(0.001)
        self.bus.write_byte_data(self.address, MODE1, mode1)
        sleep(0.005)
        self.bus.write_byte_data(self.address, MODE1, mode1 | 0x80)
        sleep(0.001)

    def deinit(self):
        try:
            self.bus.close()
        except Exception:
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
        self.pca.bus.write_byte_data(self.pca.address, base_reg, on_value & 0xFF)
        sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 1, (on_value >> 8) & 0xFF)
        sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 2, off_value & 0xFF)
        sleep(0.001)
        self.pca.bus.write_byte_data(self.pca.address, base_reg + 3, (off_value >> 8) & 0xFF)
        sleep(0.001)

class ESC:
    def __init__(self, channel, pca):
        self.channel = channel
        self.pca = pca
        self.STOP_PULSE = 1500
        self.MIN_PULSE = 1100
        self.MAX_PULSE = 1900
        self.FORWARD_MIN = 1525
        self.REVERSE_MAX = 1475
        self.current_pulse = self.STOP_PULSE

    def initialize(self):
        self._set_pulse_width(self.STOP_PULSE)
        sleep(2)
        logger.info(f"ESC on channel {self.channel} initialized")

    def set_state(self, state):
        if state > 0:
            pulse_width = self.FORWARD_MIN + (state * (self.MAX_PULSE - self.FORWARD_MIN))
        elif state < 0:
            pulse_width = self.REVERSE_MAX - (abs(state) * (self.REVERSE_MAX - self.MIN_PULSE))
        else:
            pulse_width = self.STOP_PULSE

        if pulse_width != self.current_pulse:
            self.current_pulse = pulse_width
            self._set_pulse_width(pulse_width)

    def _set_pulse_width(self, pulse_width):
        offset = 9
        pulse_width += offset
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        logger.debug(f"Channel {self.channel}: pulse {pulse_width}µs -> duty_cycle {duty_cycle}")
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        sleep(0.001)

class ESCController:
    def __init__(self, esc_channels, pca):
        self.escs = [ESC(ch, pca) for ch in esc_channels]

    def initialize_all(self):
        logger.info("Initializing all ESCs...")
        for esc in self.escs:
            esc.initialize()
        logger.info("All ESCs initialized.")

    def set_all_states(self, states):
        if len(states) != len(self.escs):
            logger.warning(f"Expected {len(self.escs)} states, got {len(states)}")
            return
        for esc, state in zip(self.escs, states):
            esc.set_state(state)

    def stop_all(self):
        for esc in self.escs:
            esc.set_state(0)

# --------------------------- Drive Calculation ---------------------------
def arcadeDrive3(x, y, rx, rT, lT) -> list[float]:
    PWM = rT - lT
    frontLeft  = -y + x + rx
    frontRight = -y - x - rx
    backRight  = y - x + rx
    backLeft   = y + x - rx
    data = [-frontLeft, -frontRight, -backLeft, -backRight]
    max_val = max(abs(v) for v in data)
    if max_val > 1.0:
        data = [v/max_val for v in data]
    # vertical thrusters
    data.extend([-PWM]*4)
    return data

# --------------------------- ROV Class without PID ---------------------------
class ROV:
    def __init__(self, control_ip='192.168.1.237', control_port=4891):
        logger.info("Initializing ROV (no PID)...")
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50
        self.esc_controller = ESCController([12,7,6,8,9,10,13,11], self.pca)
        self.esc_controller.initialize_all()
        self.controller_mapper = ControllerMapper()
        self.arm = Arm(self.pca)
        self.prev_button_states = {}
        self.left_x = self.left_y = self.right_x = 0.0
        self.left_trigger = self.right_trigger = 0.0

        self.ethernet = EthernetManager(control_ip=control_ip, control_port=control_port)
        self.ethernet.set_control_callback(self.process_command)
        self.running = False
        logger.info("ROV initialization complete.")

    def process_command(self, cmd):
        processed = False
        # Controller input handling
        if 'controller' in cmd:
            orig = cmd['controller']
            ctl = self.controller_mapper.apply_mapping(orig)
            # Extract axes
            def dz(v): return 0.0 if abs(v) < 0.05 else v
            self.left_x       = dz(ctl.get('left_stick_x', 0.0))
            self.left_y       = dz(ctl.get('left_stick_y', 0.0))
            self.right_x      = dz(ctl.get('right_stick_x',0.0))
            self.right_trigger= ctl.get('right_trigger', 0.0)
            self.left_trigger = ctl.get('left_trigger',  0.0)
            # Compute and apply motor states
            mv = arcadeDrive3(self.left_x, self.left_y, self.right_x,
                               self.right_trigger, self.left_trigger)
            self.esc_controller.set_all_states(mv)
            processed = True

        # Remap commands
        if 'remap' in cmd:
            r = cmd['remap']
            if 'source' in r and 'target' in r:
                self.controller_mapper.set_mapping(r['source'], r['target'])
                self.controller_mapper.save_mapping()
                processed = True
            elif r.get('reset', False):
                self.controller_mapper.reset_mapping()
                self.controller_mapper.save_mapping()
                processed = True

        # Arm control (buttons)
        if 'controller' in cmd:
            a = ctl.get('a',0); b = ctl.get('b',0); x = ctl.get('x',0); y = ctl.get('y',0)
            lb = ctl.get('lb',0); rb = ctl.get('rb',0)
            # Open/close claw
            if a and not self.prev_button_states.get('a',0):
                self.arm.open_claw(); processed=True
            # Button state changes
            if x and not self.prev_button_states.get('x',0):
                self.arm.set_state(ArmState.STOWED); processed=True
            if y and not self.prev_button_states.get('y',0):
                self.arm.set_state(ArmState.FULLY_OUT); processed=True
            if lb and not self.prev_button_states.get('lb',0):
                self.arm.adjust_wrist(-1, step=0.2); processed=True
            if rb and not self.prev_button_states.get('rb',0):
                self.arm.adjust_wrist(1, step=0.2); processed=True
            # Update prev
            self.prev_button_states = {'a':a,'b':b,'x':x,'y':y,'lb':lb,'rb':rb}

        return processed

    def start(self):
        logger.info("Starting ROV control server...")
        self.ethernet.start_control_server()
        self.running = True
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.shutdown()

    def shutdown(self):
        logger.info("Shutting down ROV...")
        self.running = False
        self.esc_controller.stop_all()
        try:
            self.arm.set_state(ArmState.FULLY_OUT)
            sleep(1)
        except Exception as e:
            logger.error(f"Error during arm stow: {e}")
        self.ethernet.shutdown()
        self.pca.deinit()
        logger.info("ROV shutdown complete.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Minimal ROV Control (no PID)')
    parser.add_argument('--ip',   type=str, default='192.168.1.237', help='Control server IP')
    parser.add_argument('--port', type=int, default=4891,           help='Control server port')
    parser.add_argument('--log-level', type=str, choices=['DEBUG','INFO','WARNING','ERROR'], default='INFO')
    args = parser.parse_args()
    logging.getLogger().setLevel(args.log_level)
    rov = ROV(control_ip=args.ip, control_port=args.port)
    rov.start()
