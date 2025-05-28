import os
import sys
# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# pid_system.py
import time
import numpy as np
import logging
import sys
# With these imports:
from rov.pid_controller import PID_Controller
from classesForChatPID.thruster import Thruster
from hardware.pca9685 import PCA9685

logger = logging.getLogger("PIDSystem")

class PIDSystem:
    """Manages thruster control using PID feedback for stabilization."""
    
    def __init__(self, pca: PCA9685):
        self.pca = pca
        self.thruster_channels = [0, 7, 2, 5, 1, 4, 6, 3]
        self.thruster_names = [
            "FrontLeft", "FrontLeftUp", "BackLeft", "BackLeftUp",
            "FrontRightUp", "BackRight", "BackRightUp", "FrontRight"
        ]
        self.thrusters = []
        for i, channel in enumerate(self.thruster_channels):
            name = self.thruster_names[i] if i < len(self.thruster_names) else f"Thruster{i}"
            self.thrusters.append(Thruster(channel, pca, name=name))
        # Initialize PID controllers
        self.pid_roll = PID_Controller(0, 0, 0, 0)
        self.pid_pitch = PID_Controller(0, 0, 0, 0)
        self.pid_yaw = PID_Controller(0, 0, 0, 0)
        self.pid_depth = PID_Controller(0, 0, 0, 0)
        self.pid_x = PID_Controller(0, 0, 0, 0)
        self.pid_y = PID_Controller(0, 0, 0, 0)
        self.target_speeds = [0.0] * len(self.thrusters)
        self.stabilize_enabled = True
        self.target_roll = 0.0
        self.target_pitch = 0.0
        self.target_yaw = 0.0
        self.target_depth = 0.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.axis_stabilization = {
            'x': False,
            'y': False,
            'z': True,
            'roll': True,
            'pitch': True,
            'yaw': False
        }
        self.last_controller_input = {
            'forward': 0.0,
            'strafe': 0.0, 
            'vertical': 0.0,
            'yaw': 0.0
        }
        logger.info("PID System initialized with arcadeDrive logic")
    
    def initialize(self) -> None:
        logger.info("Initializing all thrusters...")
        for thruster in self.thrusters:
            thruster.initialize()
        logger.info("Thruster initialization complete")
    
    def set_manual_speeds(self, speeds: list) -> None:
        if len(speeds) != len(self.thrusters):
            logger.error(f"Expected {len(self.thrusters)} speeds, got {len(speeds)}")
            return
        self.target_speeds = speeds
        self._update_thrusters()
        logger.debug(f"Manual speeds set: {speeds}")
    
    def set_movement(self, forward: float, strafe: float, yaw: float, vertical: float) -> None:
        forward = max(-1.0, min(1.0, forward))
        strafe = max(-1.0, min(1.0, strafe))
        yaw = max(-1.0, min(1.0, yaw))
        vertical = max(-1.0, min(1.0, vertical))
        control_input = [forward, strafe, vertical, 0.0, 0.0, yaw]
        self._calculate_thruster_values(control_input)
        self.last_controller_input = {
            'forward': forward,
            'strafe': strafe,
            'vertical': vertical,
            'yaw': yaw
        }
        logger.debug(f"Movement set: fwd={forward:.2f}, strafe={strafe:.2f}, yaw={yaw:.2f}, vert={vertical:.2f}")
    
    def _calculate_thruster_values(self, input_vector: list) -> None:
        planar_front_left = -input_vector[0] - input_vector[1] - input_vector[5]
        planar_front_right = -input_vector[0] + input_vector[1] + input_vector[5]
        planar_back_right = +input_vector[0] + input_vector[1] - input_vector[5]
        planar_back_left = +input_vector[0] - input_vector[1] + input_vector[5]
        vertical_front_left = -input_vector[2] - input_vector[3] - input_vector[4]
        vertical_front_right = -input_vector[2] + input_vector[3] - input_vector[4]
        vertical_back_left = -input_vector[2] - input_vector[3] + input_vector[4]
        vertical_back_right = -input_vector[2] + input_vector[3] + input_vector[4]

        def normalize_thrusters(thrusters):
            max_val = max(abs(t) for t in thrusters)
            if max_val > 1.0:
                thrusters = [t / max_val for t in thrusters]
            return thrusters

        planar_thrusters = normalize_thrusters([planar_front_left, planar_front_right, planar_back_right, planar_back_left])
        vertical_thrusters = normalize_thrusters([vertical_front_left, vertical_front_right, vertical_back_left, vertical_back_right])
        self.target_speeds = planar_thrusters + vertical_thrusters
        self._update_thrusters()
    
    def _update_thrusters(self) -> None:
        changes_made = False
        for i, speed in enumerate(self.target_speeds):
            if i < len(self.thrusters):
                old_speed = self.thrusters[i].current_speed
                if abs(old_speed - speed) > 0.05:
                    changes_made = True
                    logger.debug(f"Thruster {self.thrusters[i].name}: {old_speed:.2f} → {speed:.2f}")
                self.thrusters[i].set_speed(speed)
        if changes_made:
            horizontal = self.target_speeds[0:4]
            vertical = self.target_speeds[4:8]
            logger.info(f"Thruster configuration updated - Max Horizontal: {max(abs(h) for h in horizontal):.2f}, "
                        f"Max Vertical: {max(abs(v) for v in vertical):.2f}")
    
    def stop_all(self) -> None:
        logger.info("Emergency stop - all thrusters")
        for thruster in self.thrusters:
            thruster.stop()
        self.target_speeds = [0.0] * len(self.thrusters)
    
    def process_sensor_data(self, roll: float, pitch: float, yaw: float, depth: float, x: float = 0.0, y: float = 0.0) -> None:
        if not self.stabilize_enabled:
            return
        self._update_targets_from_controller()
        controller_input = [
            self.last_controller_input['forward'],
            self.last_controller_input['strafe'],
            self.last_controller_input['vertical'],
            0.0,
            0.0,
            self.last_controller_input['yaw']
        ]
        
        pid_corrections = [0.0] * 6
        if self.axis_stabilization['x']:
            pid_corrections[0] = self.pid_x.PID_Power(x, self.target_x)
        if self.axis_stabilization['y']:
            pid_corrections[1] = self.pid_y.PID_Power(y, self.target_y)
        if self.axis_stabilization['z']:
            pid_corrections[2] = self.pid_depth.PID_Power(depth, self.target_depth)
        if self.axis_stabilization['roll']:
            pid_corrections[3] = self.pid_roll.PID_Power(roll, self.target_roll)
        if self.axis_stabilization['pitch']:
            pid_corrections[4] = self.pid_pitch.PID_Power(pitch, self.target_pitch)
        if self.axis_stabilization['yaw']:
            pid_corrections[5] = self.pid_yaw.PID_Power(yaw, self.target_yaw)
        
        if any(abs(corr) > 0.05 for corr in pid_corrections):
            logger.info(f"PID Corrections: roll={pid_corrections[3]:.3f}, pitch={pid_corrections[4]:.3f}, "
                        f"yaw={pid_corrections[5]:.3f}, depth={pid_corrections[2]:.3f}")
        
        orientation_rad = [np.radians(roll), np.radians(pitch), np.radians(yaw)]
        rotated_corrections = self._rotate_vectors(pid_corrections, orientation_rad)
        combined_input = [c + p for c, p in zip(controller_input, rotated_corrections)]
        self._calculate_thruster_values(combined_input)
    
    def _rotate_vectors(self, power, orientation):
        roll, pitch, yaw = orientation
        x_rotated = (power[0] * (np.cos(yaw) * np.cos(pitch)) +
                     power[1] * (np.cos(yaw) * np.sin(pitch) * np.sin(roll) - np.sin(yaw) * np.cos(roll)) +
                     power[2] * (np.cos(yaw) * np.sin(pitch) * np.cos(roll) + np.sin(yaw) * np.sin(roll)))
        y_rotated = (power[0] * (np.sin(yaw) * np.cos(pitch)) +
                     power[1] * (np.sin(yaw) * np.sin(pitch) * np.sin(roll) + np.cos(yaw) * np.cos(roll)) +
                     power[2] * (np.sin(yaw) * np.sin(pitch) * np.cos(roll) - np.cos(yaw) * np.sin(roll)))
        z_rotated = (-power[0] * np.sin(pitch) +
                     power[1] * (np.cos(pitch) * np.sin(roll)) +
                     power[2] * (np.cos(pitch) * np.cos(roll)))
        return [x_rotated, y_rotated, z_rotated, power[3], power[4], power[5]]
    
    def _update_targets_from_controller(self):
        epsilon = sys.float_info.epsilon
        if abs(self.last_controller_input['vertical']) < 0.05:
            if not self.axis_stabilization['z']:
                logger.info(f"Depth hold activated at {self.target_depth:.2f}m")
            self.axis_stabilization['z'] = True
        else:
            self.axis_stabilization['z'] = False
        if abs(self.last_controller_input['yaw']) < 0.05:
            if not self.axis_stabilization['yaw']:
                logger.info(f"Heading hold activated at {self.target_yaw:.1f}°")
            self.axis_stabilization['yaw'] = True
        else:
            self.axis_stabilization['yaw'] = False
    
    def enable_stabilization(self, enable: bool = True) -> None:
        if self.stabilize_enabled != enable:
            self.stabilize_enabled = enable
            if enable:
                self.pid_roll.area = 0.0
                self.pid_pitch.area = 0.0
                self.pid_yaw.area = 0.0
                self.pid_depth.area = 0.0
                self.pid_x.area = 0.0
                self.pid_y.area = 0.0
                logger.info("PID stabilization enabled")
            else:
                logger.info("PID stabilization disabled")
    
    def set_targets(self, roll: float = 0.0, pitch: float = 0.0, yaw: float = None, depth: float = None) -> None:
        self.target_roll = roll
        self.target_pitch = pitch
        if yaw is not None:
            self.target_yaw = yaw
        if depth is not None:
            self.target_depth = depth
        logger.info(f"Set targets: roll={roll:.1f}, pitch={pitch:.1f}, yaw={self.target_yaw:.1f}, depth={self.target_depth:.2f}")
    
    def toggle_axis_stabilization(self, axis: str, enable: bool = None) -> None:
        if axis in self.axis_stabilization:
            if enable is None:
                self.axis_stabilization[axis] = not self.axis_stabilization[axis]
            else:
                self.axis_stabilization[axis] = enable
            logger.info(f"{axis.capitalize()} stabilization: {'enabled' if self.axis_stabilization[axis] else 'disabled'}")
    
    def shutdown(self) -> None:
        logger.info("PID System shutting down")
        self.stop_all()
        logger.info("PID System shutdown complete")
    
    def get_telemetry(self) -> dict:
        thruster_data = []
        for i, thruster in enumerate(self.thrusters):
            thruster_data.append({
                "name": thruster.name,
                "channel": thruster.channel, 
                "speed": thruster.current_speed,
                "pulse": thruster.current_pulse,
                "active_time": thruster.total_active_time,
                "direction_changes": thruster.direction_changes
            })
        pid_data = {
            "roll": {"p": self.pid_roll.P, "i": self.pid_roll.I, "d": self.pid_roll.D, "error": self.pid_roll.error},
            "pitch": {"p": self.pid_pitch.P, "i": self.pid_pitch.I, "d": self.pid_pitch.D, "error": self.pid_pitch.error},
            "yaw": {"p": self.pid_yaw.P, "i": self.pid_yaw.I, "d": self.pid_yaw.D, "error": self.pid_yaw.error},
            "depth": {"p": self.pid_depth.P, "i": self.pid_depth.I, "d": self.pid_depth.D, "error": self.pid_depth.error}
        }
        return {
            "thrusters": thruster_data,
            "stabilization_enabled": self.stabilize_enabled,
            "axis_stabilization": self.axis_stabilization,
            "targets": {"roll": self.target_roll, "pitch": self.target_pitch, "yaw": self.target_yaw, "depth": self.target_depth, "x": self.target_x, "y": self.target_y},
            "pid_data": pid_data
        }
    
    def stop_all(self) -> None:
        logger.info("Emergency stop - all thrusters")
        for thruster in self.thrusters:
            thruster.stop()
        self.target_speeds = [0.0] * len(self.thrusters)
    
    def process_sensor_data(self, roll: float, pitch: float, yaw: float, depth: float, x: float = 0.0, y: float = 0.0) -> None:
        if not self.stabilize_enabled:
            return
        self._update_targets_from_controller()
        controller_input = [
            self.last_controller_input['forward'],
            self.last_controller_input['strafe'],
            self.last_controller_input['vertical'],
            0.0,
            0.0,
            self.last_controller_input['yaw']
        ]
        pid_corrections = [0.0] * 6
        if self.axis_stabilization['x']:
            pid_corrections[0] = self.pid_x.PID_Power(x, self.target_x)
        if self.axis_stabilization['y']:
            pid_corrections[1] = self.pid_y.PID_Power(y, self.target_y)
        if self.axis_stabilization['z']:
            pid_corrections[2] = self.pid_depth.PID_Power(depth, self.target_depth)
        if self.axis_stabilization['roll']:
            pid_corrections[3] = self.pid_roll.PID_Power(roll, self.target_roll)
        if self.axis_stabilization['pitch']:
            pid_corrections[4] = self.pid_pitch.PID_Power(pitch, self.target_pitch)
        if self.axis_stabilization['yaw']:
            pid_corrections[5] = self.pid_yaw.PID_Power(yaw, self.target_yaw)
        if any(abs(corr) > 0.05 for corr in pid_corrections):
            logger.info(f"PID Corrections: roll={pid_corrections[3]:.3f}, pitch={pid_corrections[4]:.3f}, yaw={pid_corrections[5]:.3f}, depth={pid_corrections[2]:.3f}")
        orientation_rad = [np.radians(roll), np.radians(pitch), np.radians(yaw)]
        rotated_corrections = self._rotate_vectors(pid_corrections, orientation_rad)
        combined_input = [c + p for c, p in zip(controller_input, rotated_corrections)]
        self._calculate_thruster_values(combined_input)
    
    def _update_targets_from_controller(self):
        epsilon = sys.float_info.epsilon
        if abs(self.last_controller_input['vertical']) < 0.05:
            if not self.axis_stabilization['z']:
                logger.info(f"Depth hold activated at {self.target_depth:.2f}m")
            self.axis_stabilization['z'] = True
        else:
            self.axis_stabilization['z'] = False
        if abs(self.last_controller_input['yaw']) < 0.05:
            if not self.axis_stabilization['yaw']:
                logger.info(f"Heading hold activated at {self.target_yaw:.1f}°")
            self.axis_stabilization['yaw'] = True
        else:
            self.axis_stabilization['yaw'] = False
    
    def enable_stabilization(self, enable: bool = True) -> None:
        if self.stabilize_enabled != enable:
            self.stabilize_enabled = enable
            if enable:
                self.pid_roll.area = 0.0
                self.pid_pitch.area = 0.0
                self.pid_yaw.area = 0.0
                self.pid_depth.area = 0.0
                self.pid_x.area = 0.0
                self.pid_y.area = 0.0
                logger.info("PID stabilization enabled")
            else:
                logger.info("PID stabilization disabled")
    
    def set_targets(self, roll: float = 0.0, pitch: float = 0.0, yaw: float = None, depth: float = None) -> None:
        self.target_roll = roll
        self.target_pitch = pitch
        if yaw is not None:
            self.target_yaw = yaw
        if depth is not None:
            self.target_depth = depth
        logger.info(f"Set targets: roll={roll:.1f}°, pitch={pitch:.1f}°, yaw={self.target_yaw:.1f}°, depth={self.target_depth:.2f}m")
    
    def toggle_axis_stabilization(self, axis: str, enable: bool = None) -> None:
        if axis in self.axis_stabilization:
            if enable is None:
                self.axis_stabilization[axis] = not self.axis_stabilization[axis]
            else:
                self.axis_stabilization[axis] = enable
            logger.info(f"{axis.capitalize()} stabilization: {'enabled' if self.axis_stabilization[axis] else 'disabled'}")
    
    def shutdown(self) -> None:
        logger.info("PID System shutting down")
        self.stop_all()
        logger.info("PID System shutdown complete")
    
    def get_telemetry(self) -> dict:
        thruster_data = []
        for i, thruster in enumerate(self.thrusters):
            thruster_data.append({
                "name": thruster.name,
                "channel": thruster.channel,
                "speed": thruster.current_speed,
                "pulse": thruster.current_pulse,
                "active_time": thruster.total_active_time,
                "direction_changes": thruster.direction_changes
            })
        pid_data = {
            "roll": {"p": self.pid_roll.P, "i": self.pid_roll.I, "d": self.pid_roll.D, "error": self.pid_roll.error},
            "pitch": {"p": self.pid_pitch.P, "i": self.pid_pitch.I, "d": self.pid_pitch.D, "error": self.pid_pitch.error},
            "yaw": {"p": self.pid_yaw.P, "i": self.pid_yaw.I, "d": self.pid_yaw.D, "error": self.pid_yaw.error},
            "depth": {"p": self.pid_depth.P, "i": self.pid_depth.I, "d": self.pid_depth.D, "error": self.pid_depth.error}
        }
        return {
            "thrusters": thruster_data,
            "stabilization_enabled": self.stabilize_enabled,
            "axis_stabilization": self.axis_stabilization,
            "targets": {
                "roll": self.target_roll,
                "pitch": self.target_pitch,
                "yaw": self.target_yaw,
                "depth": self.target_depth,
                "x": self.target_x,
                "y": self.target_y
            },
            "pid_data": pid_data
        }
    
    def stop_all(self) -> None:
        logger.info("Emergency stop - all thrusters")
        for thruster in self.thrusters:
            thruster.stop()
        self.target_speeds = [0.0] * len(self.thrusters)
    
    def process_sensor_data(self, roll: float, pitch: float, yaw: float, depth: float, x: float = 0.0, y: float = 0.0) -> None:
        if not self.stabilize_enabled:
            return
        self._update_targets_from_controller()
        controller_input = [
            self.last_controller_input['forward'],
            self.last_controller_input['strafe'],
            self.last_controller_input['vertical'],
            0.0,
            0.0,
            self.last_controller_input['yaw']
        ]
        pid_corrections = [0.0] * 6
        if self.axis_stabilization['x']:
            pid_corrections[0] = self.pid_x.PID_Power(x, self.target_x)
        if self.axis_stabilization['y']:
            pid_corrections[1] = self.pid_y.PID_Power(y, self.target_y)
        if self.axis_stabilization['z']:
            pid_corrections[2] = self.pid_depth.PID_Power(depth, self.target_depth)
        if self.axis_stabilization['roll']:
            pid_corrections[3] = self.pid_roll.PID_Power(roll, self.target_roll)
        if self.axis_stabilization['pitch']:
            pid_corrections[4] = self.pid_pitch.PID_Power(pitch, self.target_pitch)
        if self.axis_stabilization['yaw']:
            pid_corrections[5] = self.pid_yaw.PID_Power(yaw, self.target_yaw)
        if any(abs(corr) > 0.05 for corr in pid_corrections):
            logger.info(f"PID Corrections: roll={pid_corrections[3]:.3f}, pitch={pid_corrections[4]:.3f}, yaw={pid_corrections[5]:.3f}, depth={pid_corrections[2]:.3f}")
        orientation_rad = [np.radians(roll), np.radians(pitch), np.radians(yaw)]
        rotated_corrections = self._rotate_vectors(pid_corrections, orientation_rad)
        combined_input = [c + p for c, p in zip(controller_input, rotated_corrections)]
        self._calculate_thruster_values(combined_input)
    
    def _update_targets_from_controller(self):
        epsilon = sys.float_info.epsilon
        if abs(self.last_controller_input['vertical']) < 0.05:
            if not self.axis_stabilization['z']:
                logger.info(f"Depth hold activated at {self.target_depth:.2f}m")
            self.axis_stabilization['z'] = True
        else:
            self.axis_stabilization['z'] = False
        if abs(self.last_controller_input['yaw']) < 0.05:
            if not self.axis_stabilization['yaw']:
                logger.info(f"Heading hold activated at {self.target_yaw:.1f}°")
            self.axis_stabilization['yaw'] = True
        else:
            self.axis_stabilization['yaw'] = False
    
    def enable_stabilization(self, enable: bool = True) -> None:
        if self.stabilize_enabled != enable:
            self.stabilize_enabled = enable
            if enable:
                self.pid_roll.area = 0.0
                self.pid_pitch.area = 0.0
                self.pid_yaw.area = 0.0
                self.pid_depth.area = 0.0
                self.pid_x.area = 0.0
                self.pid_y.area = 0.0
                logger.info("PID stabilization enabled")
            else:
                logger.info("PID stabilization disabled")
    
    def set_targets(self, roll: float = 0.0, pitch: float = 0.0, yaw: float = None, depth: float = None) -> None:
        self.target_roll = roll
        self.target_pitch = pitch
        if yaw is not None:
            self.target_yaw = yaw
        if depth is not None:
            self.target_depth = depth
        logger.info(f"Set targets: roll={roll:.1f}°, pitch={pitch:.1f}°, yaw={self.target_yaw:.1f}°, depth={self.target_depth:.2f}m")
    
    def toggle_axis_stabilization(self, axis: str, enable: bool = None) -> None:
        if axis in self.axis_stabilization:
            if enable is None:
                self.axis_stabilization[axis] = not self.axis_stabilization[axis]
            else:
                self.axis_stabilization[axis] = enable
            logger.info(f"{axis.capitalize()} stabilization: {'enabled' if self.axis_stabilization[axis] else 'disabled'}")
    
    def shutdown(self) -> None:
        logger.info("PID System shutting down")
        self.stop_all()
        logger.info("PID System shutdown complete")
    
    def get_telemetry(self) -> dict:
        thruster_data = []
        for i, thruster in enumerate(self.thrusters):
            thruster_data.append({
                "name": thruster.name,
                "channel": thruster.channel,
                "speed": thruster.current_speed,
                "pulse": thruster.current_pulse,
                "active_time": thruster.total_active_time,
                "direction_changes": thruster.direction_changes
            })
        pid_data = {
            "roll": {"p": self.pid_roll.P, "i": self.pid_roll.I, "d": self.pid_roll.D, "error": self.pid_roll.error},
            "pitch": {"p": self.pid_pitch.P, "i": self.pid_pitch.I, "d": self.pid_pitch.D, "error": self.pid_pitch.error},
            "yaw": {"p": self.pid_yaw.P, "i": self.pid_yaw.I, "d": self.pid_yaw.D, "error": self.pid_yaw.error},
            "depth": {"p": self.pid_depth.P, "i": self.pid_depth.I, "d": self.pid_depth.D, "error": self.pid_depth.error}
        }
        return {
            "thrusters": thruster_data,
            "stabilization_enabled": self.stabilize_enabled,
            "axis_stabilization": self.axis_stabilization,
            "targets": {"roll": self.target_roll, "pitch": self.target_pitch, "yaw": self.target_yaw, "depth": self.target_depth, "x": self.target_x, "y": self.target_y},
            "pid_data": pid_data
        }
    
    def stop_all(self) -> None:
        logger.info("Emergency stop - all thrusters")
        for thruster in self.thrusters:
            thruster.stop()
        self.target_speeds = [0.0] * len(self.thrusters)
    
    def process_sensor_data(self, roll: float, pitch: float, yaw: float, depth: float, x: float = 0.0, y: float = 0.0) -> None:
        if not self.stabilize_enabled:
            return
        self._update_targets_from_controller()
        controller_input = [
            self.last_controller_input['forward'],
            self.last_controller_input['strafe'],
            self.last_controller_input['vertical'],
            0.0,
            0.0,
            self.last_controller_input['yaw']
        ]
        pid_corrections = [0.0] * 6
        if self.axis_stabilization['x']:
            pid_corrections[0] = self.pid_x.PID_Power(x, self.target_x)
        if self.axis_stabilization['y']:
            pid_corrections[1] = self.pid_y.PID_Power(y, self.target_y)
        if self.axis_stabilization['z']:
            pid_corrections[2] = self.pid_depth.PID_Power(depth, self.target_depth)
        if self.axis_stabilization['roll']:
            pid_corrections[3] = self.pid_roll.PID_Power(roll, self.target_roll)
        if self.axis_stabilization['pitch']:
            pid_corrections[4] = self.pid_pitch.PID_Power(pitch, self.target_pitch)
        if self.axis_stabilization['yaw']:
            pid_corrections[5] = self.pid_yaw.PID_Power(yaw, self.target_yaw)
        if any(abs(corr) > 0.05 for corr in pid_corrections):
            logger.info(f"PID Corrections: roll={pid_corrections[3]:.3f}, pitch={pid_corrections[4]:.3f}, yaw={pid_corrections[5]:.3f}, depth={pid_corrections[2]:.3f}")
        orientation_rad = [np.radians(roll), np.radians(pitch), np.radians(yaw)]
        rotated_corrections = self._rotate_vectors(pid_corrections, orientation_rad)
        combined_input = [c + p for c, p in zip(controller_input, rotated_corrections)]
        self._calculate_thruster_values(combined_input)
    
    def _update_targets_from_controller(self):
        epsilon = sys.float_info.epsilon
        if abs(self.last_controller_input['vertical']) < 0.05:
            if not self.axis_stabilization['z']:
                logger.info(f"Depth hold activated at {self.target_depth:.2f}m")
            self.axis_stabilization['z'] = True
        else:
            self.axis_stabilization['z'] = False
        if abs(self.last_controller_input['yaw']) < 0.05:
            if not self.axis_stabilization['yaw']:
                logger.info(f"Heading hold activated at {self.target_yaw:.1f}°")
            self.axis_stabilization['yaw'] = True
        else:
            self.axis_stabilization['yaw'] = False
    
    def enable_stabilization(self, enable: bool = True) -> None:
        if self.stabilize_enabled != enable:
            self.stabilize_enabled = enable
            if enable:
                self.pid_roll.area = 0.0
                self.pid_pitch.area = 0.0
                self.pid_yaw.area = 0.0
                self.pid_depth.area = 0.0
                self.pid_x.area = 0.0
                self.pid_y.area = 0.0
                logger.info("PID stabilization enabled")
            else:
                logger.info("PID stabilization disabled")
    
    def set_targets(self, roll: float = 0.0, pitch: float = 0.0, yaw: float = None, depth: float = None) -> None:
        self.target_roll = roll
        self.target_pitch = pitch
        if yaw is not None:
            self.target_yaw = yaw
        if depth is not None:
            self.target_depth = depth
        logger.info(f"Set targets: roll={roll:.1f}°, pitch={pitch:.1f}°, yaw={self.target_yaw:.1f}°, depth={self.target_depth:.2f}m")
    
    def toggle_axis_stabilization(self, axis: str, enable: bool = None) -> None:
        if axis in self.axis_stabilization:
            if enable is None:
                self.axis_stabilization[axis] = not self.axis_stabilization[axis]
            else:
                self.axis_stabilization[axis] = enable
            logger.info(f"{axis.capitalize()} stabilization: {'enabled' if self.axis_stabilization[axis] else 'disabled'}")
    
    def shutdown(self) -> None:
        logger.info("PID System shutting down")
        self.stop_all()
        logger.info("PID System shutdown complete")
    
    def get_telemetry(self) -> dict:
        thruster_data = []
        for i, thruster in enumerate(self.thrusters):
            thruster_data.append({
                "name": thruster.name,
                "channel": thruster.channel, 
                "speed": thruster.current_speed,
                "pulse": thruster.current_pulse,
                "active_time": thruster.total_active_time,
                "direction_changes": thruster.direction_changes
            })
        pid_data = {
            "roll": {"p": self.pid_roll.P, "i": self.pid_roll.I, "d": self.pid_roll.D, "error": self.pid_roll.error},
            "pitch": {"p": self.pid_pitch.P, "i": self.pid_pitch.I, "d": self.pid_pitch.D, "error": self.pid_pitch.error},
            "yaw": {"p": self.pid_yaw.P, "i": self.pid_yaw.I, "d": self.pid_yaw.D, "error": self.pid_yaw.error},
            "depth": {"p": self.pid_depth.P, "i": self.pid_depth.I, "d": self.pid_depth.D, "error": self.pid_depth.error}
        }
        return {
            "thrusters": thruster_data,
            "stabilization_enabled": self.stabilize_enabled,
            "axis_stabilization": self.axis_stabilization,
            "targets": {
                "roll": self.target_roll,
                "pitch": self.target_pitch,
                "yaw": self.target_yaw,
                "depth": self.target_depth,
                "x": self.target_x,
                "y": self.target_y
            },
            "pid_data": pid_data
        }
    
    def stop_all(self) -> None:
        logger.info("Emergency stop - all thrusters")
        for thruster in self.thrusters:
            thruster.stop()
        self.target_speeds = [0.0] * len(self.thrusters)
