import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Circle, Arrow
import time
import threading
import json
import tkinter as tk
from tkinter import ttk
import os
import sys
import math
import random

# import the modules
from bno055 import BNO055  # or whatever class you need
from chatPIDARASHROV_duplicate import ROV as ArashROV
from chatPIDROV_duplicate import ROV as CustomROV

quit()

class ROVSimulator:
    """Simulator for comparing PID implementations."""
    
    def __init__(self, master):
        """Initialize the simulator."""
        self.master = master
        master.title("ROV PID Comparison Simulator")
        
        # Create mock hardware
        self.mock_pca = MockPCA9685()
        self.mock_imu = MockIMU()
        
        # Set up the frame
        self.frame = ttk.Frame(master, padding="10")
        self.frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # ROV instances (with mock hardware)
        self.arash_rov = self.create_arash_rov()
        self.custom_rov = self.create_custom_rov()

        # Figure for visualization
        self.fig = plt.figure(figsize=(12, 8))
        self.create_subplot_layout()
        
        # Animation
        self.ani = animation.FuncAnimation(
            self.fig, self.update_plot, interval=100, cache_frame_data=False)
        
        # Embed matplotlib figure in tkinter
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, columnspan=3)
        
        # Control inputs
        self.create_control_inputs()

        # Start IMU simulation thread
        self.imu_thread = threading.Thread(target=self.simulate_imu)
        self.imu_thread.daemon = True
        self.imu_thread.start()
        
        # Initialize ROVs
        self.initialize_rovs()
    
    def create_arash_rov(self):
        """Create an instance of Arash's ROV with mock hardware."""
        # We need to modify the ROV class to accept mock hardware
        rov = ArashROV(pid_enabled=True)
        # Replace hardware with mocks
        rov.pca = self.mock_pca
        rov.imu = self.mock_imu
        return rov
    
    def create_custom_rov(self):
        """Create an instance of Custom ROV with mock hardware."""
        # We need to modify the ROV class to accept mock hardware
        rov = CustomROV(pid_enabled=True)
        # Replace hardware with mocks
        rov.pca = self.mock_pca
        rov.imu = self.mock_imu
        return rov
    
    def create_subplot_layout(self):
        """Create the subplot layout for visualization."""
        # ROV diagrams (top view)
        self.ax1 = self.fig.add_subplot(221)
        self.ax1.set_title("Arash ROV (Top View)")
        self.ax1.set_xlim(-1.5, 1.5)
        self.ax1.set_ylim(-1.5, 1.5)
        self.ax1.set_aspect('equal')
        
        self.ax2 = self.fig.add_subplot(222)
        self.ax2.set_title("Custom ROV (Top View)")
        self.ax2.set_xlim(-1.5, 1.5)
        self.ax2.set_ylim(-1.5, 1.5)
        self.ax2.set_aspect('equal')
        
        # ROV diagrams (side view)
        self.ax3 = self.fig.add_subplot(223)
        self.ax3.set_title("Arash ROV (Side View)")
        self.ax3.set_xlim(-1.5, 1.5)
        self.ax3.set_ylim(-1, 1)
        self.ax3.set_aspect('equal')
        
        self.ax4 = self.fig.add_subplot(224)
        self.ax4.set_title("Custom ROV (Side View)")
        self.ax4.set_xlim(-1.5, 1.5)
        self.ax4.set_ylim(-1, 1)
        self.ax4.set_aspect('equal')
        
        self.init_rov_diagrams()
    
    def init_rov_diagrams(self):
        """Initialize the ROV diagram elements."""
        # Arash ROV Top View
        self.arash_top_frame = plt.Rectangle((-1, -0.6), 2, 1.2, fill=False, color='black')
        self.ax1.add_patch(self.arash_top_frame)
        
        # Thruster positions (top view)
        # Format: [x, y, orientation]
        self.thruster_positions_top = [
            [-0.9, 0.5, 0],    # Front Left (0)
            [0.9, 0.5, 0],     # Front Right (1)
            [-0.9, -0.5, 0],   # Back Left (2)
            [0.9, -0.5, 0]     # Back Right (3)
        ]
        
        # Create thruster visualizations (top view)
        self.arash_thrusters_top = []
        self.custom_thrusters_top = []
        
        for pos in self.thruster_positions_top:
            thruster = self.create_thruster(self.ax1, pos[0], pos[1], pos[2])
            self.arash_thrusters_top.append(thruster)
            
            thruster = self.create_thruster(self.ax2, pos[0], pos[1], pos[2])
            self.custom_thrusters_top.append(thruster)
        
        # Side view thruster positions [x, y, orientation]
        self.thruster_positions_side = [
            [-0.9, 0, 90],    # Front Left Up (4)
            [0.9, 0, 90],     # Front Right Up (5) 
            [0.9, 0, 90],     # Back Right Up (6)
            [-0.9, 0, 90]     # Back Left Up (7)
        ]
        
        # Create thruster visualizations (side view)
        self.arash_thrusters_side = []
        self.custom_thrusters_side = []
        
        for i, pos in enumerate(self.thruster_positions_side):
            # Adjust positions for side view to separate front and back
            x_offset = -0.8 if i < 2 else 0.8
            
            thruster = self.create_thruster(self.ax3, x_offset, pos[1], pos[2])
            self.arash_thrusters_side.append(thruster)
            
            thruster = self.create_thruster(self.ax4, x_offset, pos[1], pos[2])
            self.custom_thrusters_side.append(thruster)
        
        # Custom ROV Top View
        self.custom_top_frame = plt.Rectangle((-1, -0.6), 2, 1.2, fill=False, color='black')
        self.ax2.add_patch(self.custom_top_frame)
        
        # Add ROV frame to side views
        self.arash_side_frame = plt.Rectangle((-1, -0.3), 2, 0.6, fill=False, color='black')
        self.ax3.add_patch(self.arash_side_frame)
        
        self.custom_side_frame = plt.Rectangle((-1, -0.3), 2, 0.6, fill=False, color='black')
        self.ax4.add_patch(self.custom_side_frame)
        
        # Add thruster value text
        self.arash_thruster_values = []
        self.custom_thruster_values = []
        
        # Top view thruster values
        for i, pos in enumerate(self.thruster_positions_top):
            text = self.ax1.text(pos[0], pos[1]-0.2, f"T{i}: 0.00", ha='center', fontsize=8)
            self.arash_thruster_values.append(text)
            
            text = self.ax2.text(pos[0], pos[1]-0.2, f"T{i}: 0.00", ha='center', fontsize=8)
            self.custom_thruster_values.append(text)
        
        # Side view thruster values
        for i, pos in enumerate(self.thruster_positions_side):
            x_offset = -0.8 if i < 2 else 0.8
            idx = i + 4  # Thruster indices 4-7
            
            text = self.ax3.text(x_offset, pos[1]-0.2, f"T{idx}: 0.00", ha='center', fontsize=8)
            self.arash_thruster_values.append(text)
            
            text = self.ax4.text(x_offset, pos[1]-0.2, f"T{idx}: 0.00", ha='center', fontsize=8)
            self.custom_thruster_values.append(text)
        
        # Add orientation info text
        self.arash_orientation_text = self.ax1.text(0, -1.2, "H: 0° R: 0° P: 0°", ha='center')
        self.custom_orientation_text = self.ax2.text(0, -1.2, "H: 0° R: 0° P: 0°", ha='center')
    
    def create_thruster(self, ax, x, y, orientation):
        """Create a visual representation of a thruster."""
        circle = Circle((x, y), 0.1, fill=True, color='blue', alpha=0.5)
        ax.add_patch(circle)
        
        # Create a vector to show thrust
        length = 0  # Initially zero
        dx = length * math.cos(math.radians(orientation))
        dy = length * math.sin(math.radians(orientation))
        
        arrow = Arrow(x, y, dx, dy, width=0.05, color='red')
        ax.add_patch(arrow)
        
        return {'circle': circle, 'arrow': arrow, 'x': x, 'y': y, 'orientation': orientation}
    
    def create_control_inputs(self):
        """Create control input widgets."""
        control_frame = ttk.LabelFrame(self.frame, text="Simulation Controls", padding="10")
        control_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # IMU controls
        imu_frame = ttk.LabelFrame(control_frame, text="IMU Simulation", padding="10")
        imu_frame.grid(row=0, column=0, padx=10, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        ttk.Label(imu_frame, text="Roll (degrees):").grid(row=0, column=0, sticky=tk.W)
        self.roll_var = tk.DoubleVar(value=0)
        roll_scale = ttk.Scale(imu_frame, from_=-45, to=45, variable=self.roll_var, 
                               orient=tk.HORIZONTAL, length=200)
        roll_scale.grid(row=0, column=1, sticky=(tk.W, tk.E))
        ttk.Label(imu_frame, textvariable=self.roll_var).grid(row=0, column=2, width=5)
        
        ttk.Label(imu_frame, text="Pitch (degrees):").grid(row=1, column=0, sticky=tk.W)
        self.pitch_var = tk.DoubleVar(value=0)
        pitch_scale = ttk.Scale(imu_frame, from_=-45, to=45, variable=self.pitch_var, 
                                orient=tk.HORIZONTAL, length=200)
        pitch_scale.grid(row=1, column=1, sticky=(tk.W, tk.E))
        ttk.Label(imu_frame, textvariable=self.pitch_var).grid(row=1, column=2, width=5)
        
        ttk.Label(imu_frame, text="Heading (degrees):").grid(row=2, column=0, sticky=tk.W)
        self.heading_var = tk.DoubleVar(value=0)
        heading_scale = ttk.Scale(imu_frame, from_=0, to=359, variable=self.heading_var, 
                                  orient=tk.HORIZONTAL, length=200)
        heading_scale.grid(row=2, column=1, sticky=(tk.W, tk.E))
        ttk.Label(imu_frame, textvariable=self.heading_var).grid(row=2, column=2, width=5)
        
        # Controller simulation
        controller_frame = ttk.LabelFrame(control_frame, text="Controller Simulation", padding="10")
        controller_frame.grid(row=0, column=1, padx=10, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        ttk.Label(controller_frame, text="Forward:").grid(row=0, column=0, sticky=tk.W)
        self.forward_var = tk.DoubleVar(value=0)
        forward_scale = ttk.Scale(controller_frame, from_=-1, to=1, variable=self.forward_var, 
                                 orient=tk.HORIZONTAL, length=200)
        forward_scale.grid(row=0, column=1, sticky=(tk.W, tk.E))
        ttk.Label(controller_frame, textvariable=self.forward_var).grid(row=0, column=2, width=5)
        
        ttk.Label(controller_frame, text="Strafe:").grid(row=1, column=0, sticky=tk.W)
        self.strafe_var = tk.DoubleVar(value=0)
        strafe_scale = ttk.Scale(controller_frame, from_=-1, to=1, variable=self.strafe_var, 
                                 orient=tk.HORIZONTAL, length=200)
        strafe_scale.grid(row=1, column=1, sticky=(tk.W, tk.E))
        ttk.Label(controller_frame, textvariable=self.strafe_var).grid(row=1, column=2, width=5)
        
        ttk.Label(controller_frame, text="Yaw:").grid(row=2, column=0, sticky=tk.W)
        self.yaw_var = tk.DoubleVar(value=0)
        yaw_scale = ttk.Scale(controller_frame, from_=-1, to=1, variable=self.yaw_var, 
                              orient=tk.HORIZONTAL, length=200)
        yaw_scale.grid(row=2, column=1, sticky=(tk.W, tk.E))
        ttk.Label(controller_frame, textvariable=self.yaw_var).grid(row=2, column=2, width=5)
        
        ttk.Label(controller_frame, text="Vertical:").grid(row=3, column=0, sticky=tk.W)
        self.vertical_var = tk.DoubleVar(value=0)
        vertical_scale = ttk.Scale(controller_frame, from_=-1, to=1, variable=self.vertical_var, 
                                   orient=tk.HORIZONTAL, length=200)
        vertical_scale.grid(row=3, column=1, sticky=(tk.W, tk.E))
        ttk.Label(controller_frame, textvariable=self.vertical_var).grid(row=3, column=2, width=5)
        
        # PID controls
        pid_frame = ttk.LabelFrame(control_frame, text="PID Controls", padding="10")
        pid_frame.grid(row=0, column=2, padx=10, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.pid_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(pid_frame, text="Enable PID", variable=self.pid_enabled_var,
                        command=self.toggle_pid).grid(row=0, column=0, sticky=tk.W)
        
        self.heading_pid_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(pid_frame, text="Enable Heading PID", variable=self.heading_pid_var,
                        command=self.toggle_heading_pid).grid(row=1, column=0, sticky=tk.W)
        
        ttk.Button(pid_frame, text="Send Command", command=self.send_command).grid(row=2, column=0, sticky=tk.W)
        ttk.Button(pid_frame, text="Send Random IMU", command=self.random_imu).grid(row=3, column=0, sticky=tk.W)
    
    def initialize_rovs(self):
        """Initialize ROV systems."""
        # Initialize sensors and start threads
        self.arash_rov.start_orientation_thread()
        self.custom_rov.start_orientation_thread()
        
        # Set initial target heading
        self.arash_rov.target_heading = 0
        self.custom_rov.target_heading = 0
        
        # Set initial PID state
        self.toggle_pid()
        self.toggle_heading_pid()
    
    def toggle_pid(self):
        """Toggle PID stabilization."""
        enabled = self.pid_enabled_var.get()
        self.arash_rov.set_pid_enabled(enabled)
        self.custom_rov.set_pid_enabled(enabled)
    
    def toggle_heading_pid(self):
        """Toggle heading PID stabilization."""
        enabled = self.heading_pid_var.get()
        self.arash_rov.set_heading_pid_enabled(enabled)
        self.custom_rov.set_heading_pid_enabled(enabled)
    
    def send_command(self):
        """Send manual controller commands to both ROVs."""
        forward = self.forward_var.get()
        strafe = self.strafe_var.get()
        yaw = self.yaw_var.get()
        vertical = self.vertical_var.get()
        
        # Calculate motor values from joystick inputs
        # This is a simplified motor mixing logic - may need adjustment
        motor_values = [0.0] * 8
        
        # Horizontal thrusters (indices 0-3)
        motor_values[0] = forward - strafe + yaw  # FL
        motor_values[1] = forward + strafe - yaw  # FR
        motor_values[2] = forward + strafe + yaw  # BL
        motor_values[3] = forward - strafe - yaw  # BR
        
        # Vertical thrusters (indices 4-7)
        motor_values[4] = vertical  # FLU
        motor_values[5] = vertical  # FRU
        motor_values[6] = vertical  # BRU
        motor_values[7] = vertical  # BLU
        
        # Clamp values
        motor_values = [max(min(val, 1.0), -1.0) for val in motor_values]
        
        # Send to both ROVs
        command = {'motor_values': motor_values}
        self.arash_rov.process_command(command)
        self.custom_rov.process_command(command)
    
    def random_imu(self):
        """Set random IMU values for testing."""
        roll = random.uniform(-20, 20)
        pitch = random.uniform(-20, 20)
        heading = random.uniform(0, 359)
        
        self.roll_var.set(roll)
        self.pitch_var.set(pitch)
        self.heading_var.set(heading)
        
        # Update the mock IMU
        self.mock_imu.set_orientation(heading, roll, pitch)
    
    def simulate_imu(self):
        """Thread function to simulate IMU data."""
        while True:
            # Get values from UI
            roll = self.roll_var.get()
            pitch = self.pitch_var.get()
            heading = self.heading_var.get()
            
            # Update the mock IMU
            self.mock_imu.set_orientation(heading, roll, pitch)
            
            # Small sleep to reduce CPU usage
            time.sleep(0.05)
    
    def update_plot(self, frame):
        """Update the visualization with current thruster states."""
        # Update Arash ROV visualization
        arash_telemetry = self.arash_rov.pid_system.get_telemetry()
        arash_thrusters = arash_telemetry['thrusters']
        
        # Update Custom ROV visualization
        # The custom ROV doesn't have the same telemetry structure
        custom_thrusters = []
        for i, thruster in enumerate(self.custom_rov.thrusters):
            custom_thrusters.append({
                'speed': thruster.current_speed,
                'pulse': thruster.current_pulse
            })
        
        # Update thruster visualizations and values for horizontal thrusters (top view)
        for i in range(4):
            # Arash ROV
            speed = arash_thrusters[i]['speed']
            self.update_thruster_visualization(self.arash_thrusters_top[i], speed)
            self.arash_thruster_values[i].set_text(f"T{i}: {speed:.2f}")
            
            # Custom ROV
            speed = custom_thrusters[i]['speed']
            self.update_thruster_visualization(self.custom_thrusters_top[i], speed)
            self.custom_thruster_values[i].set_text(f"T{i}: {speed:.2f}")
        
        # Update thruster visualizations and values for vertical thrusters (side view)
        for i in range(4):
            idx = i + 4
            # Arash ROV
            speed = arash_thrusters[idx]['speed']
            self.update_thruster_visualization(self.arash_thrusters_side[i], speed)
            self.arash_thruster_values[idx].set_text(f"T{idx}: {speed:.2f}")
            
            # Custom ROV 
            speed = custom_thrusters[idx]['speed']
            self.update_thruster_visualization(self.custom_thrusters_side[i], speed)
            self.custom_thruster_values[idx].set_text(f"T{idx}: {speed:.2f}")
        
        # Update orientation text
        self.arash_orientation_text.set_text(
            f"H: {self.arash_rov.current_heading:.1f}° "
            f"R: {self.arash_rov.current_roll:.1f}° "
            f"P: {self.arash_rov.current_pitch:.1f}°"
        )
        
        self.custom_orientation_text.set_text(
            f"H: {self.custom_rov.current_heading:.1f}° "
            f"R: {self.custom_rov.current_roll:.1f}° "
            f"P: {self.custom_rov.current_pitch:.1f}°"
        )
        
        return []
    
    def update_thruster_visualization(self, thruster, speed):
        """Update the visual representation of a thruster based on speed."""
        # Update arrow to show thrust direction and magnitude
        x, y = thruster['x'], thruster['y']
        orientation = thruster['orientation']
        
        # Remove old arrow
        thruster['arrow'].remove()
        
        # Scale the length based on speed (-1 to 1)
        length = abs(speed) * 0.3  # Scale factor
        
        # Adjust direction if speed is negative
        if speed < 0:
            orientation += 180
        
        # Calculate vector components
        dx = length * math.cos(math.radians(orientation))
        dy = length * math.sin(math.radians(orientation))
        
        # Create new arrow
        ax = thruster['circle'].axes
        thruster['arrow'] = Arrow(x, y, dx, dy, width=0.05, 
                                  color='red' if speed > 0 else 'blue')
        ax.add_patch(thruster['arrow'])
        
        # Update circle color based on speed
        alpha = min(0.3 + abs(speed) * 0.7, 1.0)  # Vary opacity with speed
        thruster['circle'].set_alpha(alpha)

class MockPCA9685:
    """Mock PCA9685 for simulation."""
    def __init__(self):
        self.channels = [MockPWMChannel() for _ in range(16)]
        self.frequency = 50
    
    def deinit(self):
        pass

class MockPWMChannel:
    """Mock PWM Channel."""
    def __init__(self):
        self.duty_cycle = 0

class MockIMU:
    """Mock IMU sensor for simulation."""
    def __init__(self):
        self.available = True
        self.heading = 0
        self.roll = 0
        self.pitch = 0
        self.lock = threading.Lock()
    
    def set_orientation(self, heading, roll, pitch):
        """Set the orientation for simulation."""
        with self.lock:
            self.heading = heading
            self.roll = roll
            self.pitch = pitch
    
    def get_orientation(self):
        """Get the current orientation."""
        with self.lock:
            return self.heading, self.roll, self.pitch
    
    def get_calibration_status(self):
        """Return mock calibration values."""
        return (3, 3, 3, 3)
    
    def close(self):
        pass

def main():
    # Create Tkinter root
    root = tk.Tk()
    root.geometry("1200x900")
    
    # Create the simulator
    simulator = ROVSimulator(root)
    
    # Run the Tkinter main loop
    root.mainloop()

if __name__ == "__main__":
    main()