import tkinter as tk
from pyopengltk import OpenGLFrame
from OpenGL.GL import *
from OpenGL.GLU import *
import time
import math
import struct
import threading
import numpy as np
from smbus2 import SMBus

# --- BNO055 Sensor Code (Copied and slightly adapted) ---

# BNO055 Register addresses
BNO055_ADDRESS_A = 0x28
BNO055_ADDRESS_B = 0x29
BNO055_CHIP_ID = 0x00
BNO055_OPR_MODE = 0x3D
BNO055_PWR_MODE = 0x3E
BNO055_SYS_TRIGGER = 0x3F
BNO055_EULER_H_LSB = 0x1A
BNO055_QUAT_W_LSB = 0x20
BNO055_CALIB_STAT = 0x35
BNO055_TEMP = 0x34
# Add other registers if needed...

# Operation modes
BNO055_OPERATION_MODE_CONFIG = 0x00
BNO055_OPERATION_MODE_NDOF = 0x0C

# Power modes
BNO055_POWER_MODE_NORMAL = 0x00

class BNO055:
    def __init__(self, bus_number=7, address=BNO055_ADDRESS_A):
        try:
            self.bus = SMBus(bus_number)
            self.address = address
            self._connected = True
        except FileNotFoundError:
            print(f"Error: I2C bus {bus_number} not found.")
            print("Please ensure I2C is enabled and the bus number is correct.")
            self._connected = False
        except Exception as e:
            print(f"Error initializing SMBus: {e}")
            self._connected = False
        self.lock = threading.Lock() # Lock for thread-safe I2C access

    def is_connected(self):
        return self._connected

    def begin(self):
        if not self._connected:
            return False
        try:
            # Check chip ID
            chip_id = self._read_byte(BNO055_CHIP_ID)
            if chip_id != 0xA0:
                print(f"Wrong chip ID: {chip_id:02X}, expected 0xA0. Sensor not found or wrong address?")
                self._connected = False
                return False

            # Reset
            self._write_byte(BNO055_SYS_TRIGGER, 0x20)
            time.sleep(0.7) # Increased delay after reset

            # Set mode to CONFIG
            self._write_byte(BNO055_OPR_MODE, BNO055_OPERATION_MODE_CONFIG)
            time.sleep(0.025) # 19ms according to datasheet

            # Set power mode to NORMAL
            self._write_byte(BNO055_PWR_MODE, BNO055_POWER_MODE_NORMAL)
            time.sleep(0.01)

            # Use external crystal
            self._write_byte(BNO055_SYS_TRIGGER, 0x80)
            time.sleep(0.01)

            # Set mode to NDOF
            self._write_byte(BNO055_OPR_MODE, BNO055_OPERATION_MODE_NDOF)
            time.sleep(0.025) # Mode switch delay

            print("BNO055 Initialized Successfully.")
            return True
        except IOError as e:
            print(f"I/O Error during BNO055 initialization: {e}")
            self._connected = False
            return False
        except Exception as e:
            print(f"Unexpected error during BNO055 initialization: {e}")
            self._connected = False
            return False

    def get_euler(self):
        """Get Euler angles (heading/yaw, roll, pitch) in degrees"""
        if not self._connected: return (0, 0, 0)
        try:
            euler_data = self._read_registers(BNO055_EULER_H_LSB, 6)
            if euler_data is None: return (0, 0, 0)
            # Data is LSB first, 1 degree = 16 LSB
            heading = self._convert_signed_short(euler_data[0] | (euler_data[1] << 8)) / 16.0
            roll = self._convert_signed_short(euler_data[2] | (euler_data[3] << 8)) / 16.0
            pitch = self._convert_signed_short(euler_data[4] | (euler_data[5] << 8)) / 16.0
            return (heading, roll, pitch)
        except IOError as e:
            print(f"I/O Error reading Euler angles: {e}")
            self._connected = False # Assume connection lost on error
            return (0, 0, 0)
        except Exception as e:
            print(f"Unexpected error reading Euler angles: {e}")
            return (0, 0, 0)

    def get_calibration(self):
        """Get calibration status (sys, gyro, accel, mag)"""
        if not self._connected: return (0, 0, 0, 0)
        try:
            calib_stat = self._read_byte(BNO055_CALIB_STAT)
            if calib_stat is None: return (0, 0, 0, 0)
            sys = (calib_stat >> 6) & 0x03
            gyro = (calib_stat >> 4) & 0x03
            accel = (calib_stat >> 2) & 0x03
            mag = calib_stat & 0x03
            return (sys, gyro, accel, mag)
        except IOError as e:
            print(f"I/O Error reading calibration status: {e}")
            self._connected = False
            return (0, 0, 0, 0)
        except Exception as e:
            print(f"Unexpected error reading calibration status: {e}")
            return (0, 0, 0, 0)

    def get_temp(self):
        """Get temperature in Celsius"""
        if not self._connected: return 0
        try:
            temp = self._read_byte(BNO055_TEMP)
            return temp if temp is not None else 0
        except IOError as e:
            print(f"I/O Error reading temperature: {e}")
            self._connected = False
            return 0
        except Exception as e:
            print(f"Unexpected error reading temperature: {e}")
            return 0

    def _read_byte(self, register):
        with self.lock:
            try:
                return self.bus.read_byte_data(self.address, register)
            except IOError as e:
                # Don't print repetitive errors here, handle in calling function
                # print(f"I/O error reading byte from register {register:02X}: {e}")
                raise e # Re-raise to be caught by caller
            except Exception as e:
                print(f"Unexpected error reading byte from register {register:02X}: {e}")
                raise e

    def _write_byte(self, register, value):
        with self.lock:
            try:
                self.bus.write_byte_data(self.address, register, value)
                return True
            except IOError as e:
                print(f"I/O error writing byte to register {register:02X}: {e}")
                self._connected = False # Assume connection lost
                return False
            except Exception as e:
                print(f"Unexpected error writing byte to register {register:02X}: {e}")
                return False

    def _read_registers(self, register, length):
        with self.lock:
            try:
                return self.bus.read_i2c_block_data(self.address, register, length)
            except IOError as e:
                # Don't print repetitive errors here, handle in calling function
                # print(f"I/O error reading block from register {register:02X}: {e}")
                raise e # Re-raise to be caught by caller
            except Exception as e:
                print(f"Unexpected error reading block from register {register:02X}: {e}")
                raise e

    def _convert_signed_short(self, value):
        """Convert a 16-bit unsigned value read from sensor to a signed short"""
        if value >= 32768: # Check if the sign bit (15) is set
            return value - 65536
        else:
            return value

    def close(self):
        if self._connected and hasattr(self, 'bus'):
            try:
                # Attempt to put sensor in low power mode? Optional.
                # self._write_byte(BNO055_OPR_MODE, BNO055_OPERATION_MODE_CONFIG)
                # time.sleep(0.025)
                # self._write_byte(BNO055_PWR_MODE, BNO055_POWER_MODE_SUSPEND) # Or Low Power
                self.bus.close()
                print("I2C bus closed.")
            except Exception as e:
                print(f"Error closing I2C bus: {e}")
        self._connected = False


# --- Cube Vertices and Edges ---
vertices = (
    ( 1, -1, -1), ( 1,  1, -1), (-1,  1, -1), (-1, -1, -1),
    ( 1, -1,  1), ( 1,  1,  1), (-1, -1,  1), (-1,  1,  1)
)
edges = (
    (0, 1), (0, 3), (0, 4), (2, 1), (2, 3), (2, 7),
    (6, 3), (6, 4), (6, 7), (5, 1), (5, 4), (5, 7)
)
surfaces = (
    (0, 1, 2, 3), # Back
    (3, 2, 7, 6), # Left
    (6, 7, 5, 4), # Front
    (4, 5, 1, 0), # Right
    (1, 5, 7, 2), # Top
    (4, 0, 3, 6)  # Bottom
)
colors = (
    (1, 0, 0), (0, 1, 0), (0, 0, 1), # R, G, B
    (1, 1, 0), (1, 0, 1), (0, 1, 1)  # Y, M, C
)

# --- OpenGL Visualization Frame ---
class CubeVisualizerFrame(OpenGLFrame):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.animate = 10 # Milliseconds between redraws
        self.heading = 0.0
        self.roll = 0.0
        self.pitch = 0.0
        self.is_drawing = False # Prevent redraw overlaps

    def initgl(self):
        """Initialize OpenGL settings"""
        glViewport(0, 0, self.width, self.height)
        glClearColor(0.8, 0.8, 0.9, 1.0) # Light background
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_POSITION, (0, 5, 5, 1)) # Light position
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (1.0, 1.0, 1.0, 1.0)) # White light
        glEnable(GL_COLOR_MATERIAL) # Enable coloring
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, (self.width / self.height), 0.1, 50.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(0, 0, 10,  # Camera position (eye)
                  0, 0, 0,  # Target position (center)
                  0, 1, 0)  # Up vector

    def redraw(self):
        """Called by the timer to redraw the scene"""
        if self.is_drawing:
            return # Skip if already drawing
        self.is_drawing = True

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        gluLookAt(0, 0, 10, 0, 0, 0, 0, 1, 0) # Reset view

        # Apply rotations - Order matters! (Yaw, Pitch, Roll is common)
        # OpenGL rotations are in degrees
        glRotatef(self.heading, 0, 1, 0) # Yaw around Y axis
        glRotatef(self.pitch, 1, 0, 0)   # Pitch around X axis
        glRotatef(self.roll, 0, 0, 1)    # Roll around Z axis (pointing out)

        self.draw_cube()
        glFlush() # Ensure commands are executed

        self.is_drawing = False

    def draw_cube(self):
        """Draws the colored cube"""
        glBegin(GL_QUADS)
        for i, surface in enumerate(surfaces):
            glColor3fv(colors[i % len(colors)]) # Cycle through colors
            for vertex_index in surface:
                glVertex3fv(vertices[vertex_index])
        glEnd()

        # Optional: Draw edges for clarity
        # glColor3f(0, 0, 0) # Black edges
        # glBegin(GL_LINES)
        # for edge in edges:
        #     for vertex_index in edge:
        #         glVertex3fv(vertices[vertex_index])
        # glEnd()

    def update_orientation(self, heading, roll, pitch):
        """Update the angles for the next redraw"""
        # Adjust BNO055 axes/signs if necessary to match OpenGL coordinate system
        # Default OpenGL: +X right, +Y up, +Z out of screen
        # BNO055 default: Depends on mounting, check datasheet
        # Assuming direct mapping for now:
        self.heading = -heading
        self.roll = roll # Often roll needs inversion depending on definition
        self.pitch = -pitch

# --- Main Application Class ---
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("BNO055 Orientation Visualizer")

        # Sensor setup
        self.bno = BNO055(bus_number=7, address=BNO055_ADDRESS_A)
        if not self.bno.is_connected() or not self.bno.begin():
            print("Exiting due to BNO055 initialization failure.")
            # Show error in GUI instead of just console
            error_label = tk.Label(root, text="Failed to initialize BNO055 sensor.\nCheck connection and I2C setup.", fg="red", font=("Arial", 14))
            error_label.pack(pady=20, padx=20)
            self.sensor_running = False
            self.root.after(5000, self.root.destroy) # Close after 5s
            return # Stop further initialization
        else:
             self.sensor_running = True


        # GUI setup
        self.root.geometry("600x700")

        # OpenGL Frame
        self.gl_frame = CubeVisualizerFrame(root, width=550, height=500)
        self.gl_frame.pack(pady=10)

        # Info Labels Frame
        self.info_frame = tk.Frame(root)
        self.info_frame.pack(pady=5)

        self.euler_label = tk.Label(self.info_frame, text="Euler: H=0.00, R=0.00, P=0.00", font=("Arial", 12))
        self.euler_label.grid(row=0, column=0, padx=10, sticky="w")

        self.calib_label = tk.Label(self.info_frame, text="Calib: S=0, G=0, A=0, M=0", font=("Arial", 12))
        self.calib_label.grid(row=1, column=0, padx=10, sticky="w")

        self.temp_label = tk.Label(self.info_frame, text="Temp: 0°C", font=("Arial", 12))
        self.temp_label.grid(row=2, column=0, padx=10, sticky="w")

        # Sensor reading thread
        self.sensor_thread = threading.Thread(target=self.read_sensor_loop, daemon=True)
        self.sensor_thread.start()

        # Close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def read_sensor_loop(self):
        """Continuously reads sensor data in a background thread"""
        while self.sensor_running:
            if not self.bno.is_connected():
                print("Sensor disconnected. Stopping sensor thread.")
                self.sensor_running = False
                # Update GUI to show error state
                self.root.after(0, self.update_gui_disconnected)
                break

            try:
                # Read data
                heading, roll, pitch = self.bno.get_euler()
                sys, gyro, accel, mag = self.bno.get_calibration()
                temp = self.bno.get_temp()

                # Update OpenGL frame (thread-safe via Tkinter's event loop)
                self.root.after(0, self.gl_frame.update_orientation, heading, roll, pitch)

                # Update info labels (thread-safe via Tkinter's event loop)
                self.root.after(0, self.update_info_labels, heading, roll, pitch, sys, gyro, accel, mag, temp)

                time.sleep(0.05) # Read around 20Hz

            except Exception as e:
                print(f"Error in sensor read loop: {e}")
                # Consider adding a small delay or attempting reconnect here
                time.sleep(1) # Wait a bit before retrying after an error

        print("Sensor reading loop finished.")
        self.bno.close()

    def update_info_labels(self, h, r, p, s, g, a, m, temp):
        """Updates the text labels in the GUI (called via root.after)"""
        self.euler_label.config(text=f"Euler: H={h:6.2f}, R={r:6.2f}, P={p:6.2f}")
        self.calib_label.config(text=f"Calib: S={s}, G={g}, A={a}, M={m}")
        self.temp_label.config(text=f"Temp: {temp}°C")

    def update_gui_disconnected(self):
        """Updates GUI elements when sensor disconnects"""
        self.euler_label.config(text="Euler: ---.--, ---.--, ---.--", fg="red")
        self.calib_label.config(text="Calib: S=-, G=-, A=-, M=-", fg="red")
        self.temp_label.config(text="Temp: --°C", fg="red")
        # Optionally disable or change the OpenGL view


    def on_closing(self):
        """Handles window close event"""
        print("Closing application...")
        self.sensor_running = False # Signal the thread to stop
        # Wait briefly for the thread to potentially finish its current loop
        # A more robust solution would use thread joining with a timeout
        time.sleep(0.2)
        # The BNO close is now handled within the thread when it exits
        # self.bno.close() # Ensure sensor connection is closed
        self.root.destroy()

# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    if app.sensor_running: # Only start mainloop if sensor init was okay
        root.mainloop()
    else:
        print("Application did not start fully due to sensor issues.")
        # The error message should already be visible in the GUI window
        # Keep the window open briefly if it was created
        if root.winfo_exists():
             root.mainloop() # Keep error window open until closed manually or by timer
