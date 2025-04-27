# rov.py
import time
import logging
import threading
import argparse
from sensor import Sensor
from ethernet_manager import EthernetManager
from arm import Arm, ArmState
from pid_system import PIDSystem
from tools import Bucket, Net, Syringe
from hardware.pca9685 import PCA9685

logger = logging.getLogger("ROV")

class ROV:
    """Main ROV system that manages all components"""
    def __init__(self):
        logger.info("Initializing ROV system...")
        self.pca = PCA9685(bus_number=7)
        self.pca.frequency = 50
        logger.info("Initializing subsystems...")
        self.arm = Arm(self.pca)
        self.pid_system = PIDSystem(self.pca)
        self.ethernet = EthernetManager()
        self.sensors = Sensor()
        self.bucket = Bucket(self.pca)
        self.net = Net(self.pca)
        self.syringe = Syringe(self.pca)
        self.running = False
        self.last_telemetry_time = 0
        self.telemetry_interval = 0.2
        self.stabilization_enabled = True
        self.ethernet.set_control_callback(self._process_control_data)
        logger.info("ROV system initialization complete")
    
    def start(self) -> None:
        logger.info("Starting ROV system...")
        self.pid_system.initialize()
        self.arm.initialize()
        self.ethernet.start_control_server()
        self.sensors.start()
        self.running = True
        logger.info("ROV system started")
        self._main_loop()
    
    def _main_loop(self) -> None:
        logger.info("Entering main control loop")
        while self.running:
            try:
                if self.stabilization_enabled:
                    self._update_stabilization()
                current_time = time.time()
                if current_time - self.last_telemetry_time >= self.telemetry_interval:
                    self._send_telemetry()
                    self.last_telemetry_time = current_time
                time.sleep(0.01)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(0.5)
    
    def _send_telemetry(self) -> None:
        telemetry = {
            "sensors": self.sensors.get_telemetry(),
            "arm_state": self.arm.current_state.name,
            "thrusters": self.pid_system.get_telemetry(),
            "tools": {
                "bucket": self.bucket.current_state,
                "net": self.net.current_state,
                "syringe": self.syringe.current_state
            },
            "stabilization": self.stabilization_enabled
        }
        self.ethernet.send_telemetry(telemetry)
    
    def _process_control_data(self, control_data: dict) -> None:
        try:
            if 'stabilization' in control_data:
                enable = control_data['stabilization'].get('enable', None)
                if enable is not None:
                    self.stabilization_enabled = enable
                    self.pid_system.enable_stabilization(enable)
                    logger.info(f"Stabilization {'enabled' if enable else 'disabled'}")
                if 'targets' in control_data['stabilization']:
                    targets = control_data['stabilization']['targets']
                    roll = targets.get('roll', 0.0)
                    pitch = targets.get('pitch', 0.0)
                    yaw = targets.get('yaw', None)
                    depth = targets.get('depth', None)
                    self.pid_system.set_targets(roll, pitch, yaw, depth)
            if 'motor_values' in control_data:
                motor_values = control_data['motor_values']
                if isinstance(motor_values, list) and len(motor_values) == 8:
                    self.pid_system.set_manual_speeds(motor_values)
                    logger.debug("Updated thruster speeds")
            if 'movement' in control_data:
                movement = control_data['movement']
                forward = movement.get('forward', 0.0)
                strafe = movement.get('strafe', 0.0)
                yaw = movement.get('yaw', 0.0)
                vertical = movement.get('vertical', 0.0)
                self.pid_system.set_movement(forward, strafe, yaw, vertical)
                logger.debug("Updated movement commands")
            if 'buttons' in control_data or 'hats' in control_data:
                buttons = control_data.get('buttons', [])
                prev_buttons = control_data.get('prev_buttons', [0] * len(buttons))
                hats = control_data.get('hats', [(0, 0)])
                prev_hats = control_data.get('prev_hats', hats)
                self.arm.process_controller_input(buttons, prev_buttons, hats, prev_hats)
                if len(buttons) > 7:
                    if buttons[7] == 1 and (len(prev_buttons) <= 7 or prev_buttons[7] == 0):
                        self.bucket.activate()
                    if len(buttons) > 8 and buttons[8] == 1 and (len(prev_buttons) <= 8 or prev_buttons[8] == 0):
                        self.net.activate()
                    if len(buttons) > 9 and buttons[9] == 1 and (len(prev_buttons) <= 9 or prev_buttons[9] == 0):
                        self.syringe.activate()
        except Exception as e:
            logger.error(f"Error processing control data: {e}")
    
    def _update_stabilization(self) -> None:
        if self.stabilization_enabled:
            roll, pitch, yaw = self.sensors.get_orientation()
            depth = self.sensors.get_depth()
            logger.debug(f"Stabilization: Roll={roll:.1f}°, Pitch={pitch:.1f}°, Yaw={yaw:.1f}°, Depth={depth:.2f}m")
            self.pid_system.process_sensor_data(roll, pitch, yaw, depth)
    
    def shutdown(self) -> None:
        logger.info("ROV system shutting down...")
        self.running = False
        self.pid_system.enable_stabilization(False)
        self.pid_system.stop_all()
        self.arm.shutdown()
        self.sensors.shutdown()
        self.ethernet.shutdown()
        self.bucket.shutdown()
        self.net.shutdown()
        self.syringe.shutdown()
        self.pca.deinit()
        logger.info("ROV system shutdown complete")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='ROV Control System')
    parser.add_argument('--log-level', type=str, default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')
    args = parser.parse_args()
    logging.getLogger().setLevel(args.log_level)
    rov = ROV()
    try:
        rov.start()
    except KeyboardInterrupt:
        logger.info("ROV system interrupted by user")
        rov.shutdown()
    except Exception as e:
        logger.error(f"Error in ROV system: {e}")
        rov.shutdown()

if __name__ == '__main__':
    main()
