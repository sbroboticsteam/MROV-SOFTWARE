import tkinter as tk
from pyopengltk import OpenGLFrame
from OpenGL.GL import *
from OpenGL.GLU import *
import time
import math
import struct
import threading
import numpy as np

# --- Import BNO055 class and necessary constants ---
# Ensure bno055.py is in the same directory
try:
    from bno055 import BNO055, BNO055_ADDRESS_A, BNO055_OPERATION_MODE_NDOF, BNO055_OPERATION_MODE_CONFIG, BNO055_POWER_MODE_NORMAL, BNO055_SYS_TRIGGER, BNO055_CHIP_ID, BNO055_PWR_MODE, BNO055_OPR_MODE, BNO055_EULER_H_LSB, BNO055_CALIB_STAT, BNO055_TEMP
except ImportError:
    print("Error: Could not import from bno055.py.")
    print("Please ensure bno055.py is in the same directory as this script.")
    exit()
except Exception as e:
    print(f"An unexpected error occurred during import: {e}")
    exit()


# --- ROV Geometry Definitions ---
plate_side = 2.0        # Side length of square top/bottom plates
plate_separation = 1.0  # Vertical distance between plates (H)
connector_width = 0.2   # Width of the connecting plates/braces
connector_inset = 0.3   # How far connectors are moved in from the absolute corner

motor_radius = 0.15
motor_height = 0.3
motor_color = (0.3, 0.3, 0.3) # Dark grey for motors
plate_color_top = (0.8, 0.8, 0.8)
plate_color_bottom = (0.6, 0.6, 0.6)
connector_color = (0.7, 0.7, 0.7)

# --- Calculate Derived Geometry ---
hs = plate_side / 2.0   # Half side length
h_sep = plate_separation / 2.0 # Half separation (for y coordinates)
hcw = connector_width / 2.0 # Half connector width

# --- Vertices for Top/Bottom Plates (Now Square) ---
top_plate_vertices = [
    ( hs, h_sep,  hs), (-hs, h_sep,  hs), (-hs, h_sep, -hs), ( hs, h_sep, -hs)
]
bottom_plate_vertices = [
    ( hs, -h_sep,  hs), (-hs, -h_sep,  hs), (-hs, -h_sep, -hs), ( hs, -h_sep, -hs)
]

# --- Data for Connecting Plates (Inset and Rotated 45 deg) ---
connector_verts_list = [] # List of 4 vertex lists (each defining a connector quad)
connector_normals_list = [] # List of 4 normal vectors for the connectors
connector_centers_list = [] # List of center points for each connector

# Base XZ coordinates for the *center* of the connector's attachment line on the plates
inset_corner_coords_xz = [
    ( hs - connector_inset,  hs - connector_inset),
    (-hs + connector_inset,  hs - connector_inset),
    (-hs + connector_inset, -hs + connector_inset),
    ( hs - connector_inset, -hs + connector_inset)
]
# Outward-pointing normals at 45 degrees in XZ plane (remain the same direction)
corner_normals_xz = [(1, 1), (-1, 1), (-1, -1), (1, -1)]

for i in range(4):
    # Center point for the connector's line on the plate
    center_x, center_z = inset_corner_coords_xz[i]

    # Normal vector calculation (same as before)
    nx_xz, nz_xz = corner_normals_xz[i]
    norm_len = math.sqrt(nx_xz**2 + nz_xz**2)
    nx, nz = nx_xz / norm_len, nz_xz / norm_len
    connector_normals_list.append((nx, 0, nz)) # Store the normal vector (Y=0)

    # Calculate the direction vector for the plate's width (tangent)
    width_dx, width_dz = -nz, nx # Perpendicular vector in XZ plane

    # Calculate the 4 vertices for this connector plate based on the center and width
    v1 = (center_x + width_dx * hcw,  h_sep, center_z + width_dz * hcw) # Top-Tangent1
    v2 = (center_x - width_dx * hcw,  h_sep, center_z - width_dz * hcw) # Top-Tangent2
    v3 = (center_x - width_dx * hcw, -h_sep, center_z - width_dz * hcw) # Bottom-Tangent2
    v4 = (center_x + width_dx * hcw, -h_sep, center_z + width_dz * hcw) # Bottom-Tangent1
    connector_verts_list.append([v1, v2, v3, v4])

    # Calculate and store the center point of this connector face
    connector_center_x = (v1[0] + v2[0] + v3[0] + v4[0]) / 4.0
    connector_center_y = 0 # (v1[1] + v2[1] + v3[1] + v4[1]) / 4.0 should be 0
    connector_center_z = (v1[2] + v2[2] + v3[2] + v4[2]) / 4.0
    connector_centers_list.append((connector_center_x, connector_center_y, connector_center_z))


# --- Data for Motors ---
# Top motors (square pattern, pointing up) - Closer to center
top_motor_spacing = plate_side * 0.25 # Reduced multiplier
top_motor_y_base = h_sep # Base rests on the top plate
top_motor_positions = [ # Center coordinates for the base of the motor
    ( top_motor_spacing, top_motor_y_base,  top_motor_spacing),
    (-top_motor_spacing, top_motor_y_base,  top_motor_spacing),
    (-top_motor_spacing, top_motor_y_base, -top_motor_spacing),
    ( top_motor_spacing, top_motor_y_base, -top_motor_spacing),
]

# Side motors (mounted sideways on outward face of connector plates)
side_motor_positions = [] # Center coordinates for the *base* of the motor
side_motor_orientations = [] # Store rotation sequence

# Calculate orientation for side motors
for i in range(4):
    center_x, center_y, center_z = connector_centers_list[i]
    nx, _, nz = connector_normals_list[i]
    # Tangent direction along connector width: (-nz, 0, nx)
    tangent_x, tangent_z = -nz, nx

    # Position the *center of the motor's base* on the outward face
    # Offset from the connector center along the normal by the motor radius
    base_center_x = center_x + nx * motor_radius
    base_center_y = center_y # Keep at Y=0 (middle of connector height)
    base_center_z = center_z + nz * motor_radius
    side_motor_positions.append((base_center_x, base_center_y, base_center_z))

    # Orientation:
    # Rotate around the global Y-axis so the cylinder's length (default Z)
    # aligns with the connector plate's tangent direction (tangent_x, 0, tangent_z).
    angle_y_rad = math.atan2(tangent_x, tangent_z) # atan2(x, z) gives angle from +Z towards +X
    angle_y_deg = math.degrees(angle_y_rad)

    # Store only the Y rotation needed to align length with tangent
    side_motor_orientations.append({'angle_y': angle_y_deg, 'axis_y': (0, 1, 0)})


# --- OpenGL Visualization Frame ---
class ROVVisualizerFrame(OpenGLFrame):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.animate = 10 # Milliseconds between redraws
        self.heading = 0.0
        self.roll = 0.0
        self.pitch = 0.0
        self.is_drawing = False # Prevent redraw overlaps
        self.q = None # Initialize quadric object holder

    def initgl(self):
        """Initialize OpenGL settings"""
        try:
            self.q = gluNewQuadric() # Quadric object for drawing cylinders/disks
            if not self.q:
                 raise RuntimeError("gluNewQuadric failed to return a valid object.")
            gluQuadricNormals(self.q, GLU_SMOOTH) # Generate normals for lighting
            gluQuadricTexture(self.q, GL_FALSE) # No texturing needed
        except Exception as e:
            print(f"Error creating or configuring quadric: {e}. Lighting/drawing on motors may be affected.")
            self.q = None # Ensure q is None if setup failed

        glViewport(0, 0, self.width, self.height)
        glClearColor(0.8, 0.8, 0.9, 1.0) # Light background
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_POSITION, (5, 10, 15, 1)) # Adjusted light position
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (1.0, 1.0, 1.0, 1.0)) # White light
        glEnable(GL_COLOR_MATERIAL) # Enable coloring based on glColor
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_NORMALIZE) # Normalize normals after transformations

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, (self.width / self.height) if self.height > 0 else 1, 0.1, 50.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(0, 0, 12,  # Camera position (eye) - Moved back slightly
                  0, 0, 0,  # Target position (center)
                  0, 1, 0)  # Up vector

    def redraw(self):
        """Called by the timer to redraw the scene"""
        if self.is_drawing: return
        self.is_drawing = True

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        gluLookAt(0, 0, 12, 0, 0, 0, 0, 1, 0) # Reset view

        # Apply sensor rotations (Yaw, Pitch, Roll)
        glRotatef(self.heading, 0, 1, 0) # Yaw around Y
        glRotatef(self.pitch, 1, 0, 0)   # Pitch around X
        glRotatef(self.roll, 0, 0, 1)    # Roll around Z

        # Draw the ROV components
        self.draw_plates()
        self.draw_connectors()
        self.draw_top_motors()
        self.draw_side_motors()

        glFlush() # Ensure commands are executed
        self.is_drawing = False

    def draw_plates(self):
        """Draws the top and bottom square plates"""
        # Draw Top Plate
        glColor3fv(plate_color_top)
        glNormal3f(0, 1, 0) # Normal points up
        glBegin(GL_QUADS)
        for v in top_plate_vertices: glVertex3fv(v)
        glEnd()

        # Draw Bottom Plate
        glColor3fv(plate_color_bottom)
        glNormal3f(0, -1, 0) # Normal points down
        glBegin(GL_QUADS)
        # Reverse vertex order for correct facing/normal calculation by OpenGL
        for v in reversed(bottom_plate_vertices): glVertex3fv(v)
        glEnd()

    def draw_connectors(self):
        """Draws the four inset connecting plates/braces"""
        glColor3fv(connector_color)
        for i in range(4):
            verts = connector_verts_list[i]
            normal = connector_normals_list[i]
            glNormal3fv(normal) # Set normal for the face
            glBegin(GL_QUADS)
            for v in verts: glVertex3fv(v)
            glEnd()

    def draw_top_motors(self):
        """Draws the four motors on the top plate"""
        if not self.q: return # Cannot draw cylinders if quadric failed
        glColor3fv(motor_color)
        for x, y, z in top_motor_positions:
            glPushMatrix()
            # Translate to the base center of the motor
            glTranslatef(x, y, z)
            # Rotate the cylinder so its axis aligns with +Y (up)
            glRotatef(-90, 1, 0, 0) # Rotate -90 deg around X-axis
            # Draw the cylinder body
            gluCylinder(self.q, motor_radius, motor_radius, motor_height, 16, 1)
            # Draw end caps
            gluDisk(self.q, 0, motor_radius, 16, 1) # Base cap at z=0
            glTranslatef(0, 0, motor_height) # Move to the top end
            gluDisk(self.q, 0, motor_radius, 16, 1) # Top cap at z=motor_height
            glPopMatrix()

    def draw_side_motors(self):
        """Draws the four motors mounted sideways on the connector plates"""
        if not self.q: return
        glColor3fv(motor_color)
        for i in range(4):
            x, y, z = side_motor_positions[i] # Center of motor base on outward face
            orientation = side_motor_orientations[i]

            glPushMatrix()
            # Translate to the desired center point on the connector face
            glTranslatef(x, y, z)

            # Apply the Y rotation to align cylinder length (Z) with connector tangent
            glRotatef(orientation['angle_y'], *orientation['axis_y']) # Rotate around global Y

            # Translate along the cylinder's new Z-axis by -height/2
            # This shifts the cylinder so its midpoint is at the (x,y,z) position
            glTranslatef(0, 0, -motor_height / 2.0)

            # Draw the cylinder body (default axis is Z)
            # Its length is now horizontal, parallel to the connector plate width.
            # Its midpoint is now at the desired location on the connector face.
            gluCylinder(self.q, motor_radius, motor_radius, motor_height, 16, 1)
            # Draw end caps relative to the shifted cylinder
            gluDisk(self.q, 0, motor_radius, 16, 1) # Base cap (at the translated origin - height/2)
            glTranslatef(0, 0, motor_height) # Move along the cylinder's length axis
            gluDisk(self.q, 0, motor_radius, 16, 1) # End cap (at the translated origin + height/2)
            glPopMatrix()

    def update_orientation(self, heading, roll, pitch):
        """Update the angles for the next redraw"""
        # Apply inversions as determined previously
        self.heading = -heading
        self.roll = roll # Assuming roll did not need inversion based on previous steps
        self.pitch = -pitch

    def __del__(self):
        # Clean up the quadric object when the frame is destroyed
        if hasattr(self, 'q') and self.q:
            try:
                gluDeleteQuadric(self.q)
                self.q = None
            except Exception as e:
                pass # Ignore errors during cleanu


# --- Main Application Class ---
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("BNO055 ROV Visualizer")

        # Sensor setup
        self.bno = None
        self.sensor_running = False
        try:
            # Initialize BNO055 object
            self.bno = BNO055(bus_number=7, address=BNO055_ADDRESS_A)
            # Attempt to begin communication and setup
            if not self.bno.begin():
                raise RuntimeError("BNO055 begin() failed. Check connection/setup.")
            self.sensor_running = True
        except Exception as e:
            # Catch errors during __init__ or begin()
            print(f"Error initializing BNO055: {e}")
            error_text = f"Failed to initialize BNO055 sensor.\n{e}\nCheck connection and I2C setup."
            error_label = tk.Label(root, text=error_text, fg="red", font=("Arial", 12), justify=tk.LEFT)
            error_label.pack(pady=20, padx=20)
            self.sensor_running = False
            return # Stop further initialization if sensor failed

        # GUI setup (only if sensor init succeeded)
        self.root.geometry("600x700")

        # OpenGL Frame
        self.gl_frame = ROVVisualizerFrame(root, width=550, height=550)
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
            # Check if bno object exists (it should if init succeeded)
            if not self.bno:
                print("BNO object not initialized. Stopping sensor thread.")
                self.sensor_running = False
                self.root.after(0, self.update_gui_disconnected)
                break

            try:
                # Attempt to read data. IOErrors during reads will indicate disconnection.
                heading, roll, pitch = self.bno.get_euler()
                sys, gyro, accel, mag = self.bno.get_calibration()
                temp = self.bno.get_temp()

                # Schedule updates in the main GUI thread
                self.root.after(0, self.gl_frame.update_orientation, heading, roll, pitch)
                self.root.after(0, self.update_info_labels, heading, roll, pitch, sys, gyro, accel, mag, temp)

                time.sleep(0.05) # Read around 20Hz

            except IOError as e:
                # Specific handling for I/O errors, likely indicating disconnection
                print(f"I/O Error in sensor read loop (possible disconnection): {e}")
                self.sensor_running = False
                self.root.after(0, self.update_gui_disconnected)
                break # Exit loop
            except Exception as e:
                # Catch other unexpected errors during sensor reading
                print(f"Unexpected error in sensor read loop: {e}")
                self.sensor_running = False
                self.root.after(0, self.update_gui_disconnected)
                break # Exit loop

        print("Sensor reading loop finished.")
        if self.bno:
            # Attempt to close the bus connection if the object exists
            try:
                self.bno.close()
            except Exception as e:
                print(f"Error closing BNO055: {e}")

    def update_info_labels(self, h, r, p, s, g, a, m, temp):
        """Updates the text labels in the GUI (called via root.after)"""
        if not self.root.winfo_exists(): return # Check if window still exists
        self.euler_label.config(text=f"Euler: H={h:6.2f}, R={r:6.2f}, P={p:6.2f}")
        self.calib_label.config(text=f"Calib: S={s}, G={g}, A={a}, M={m}")
        self.temp_label.config(text=f"Temp: {temp}°C")

    def update_gui_disconnected(self):
        """Updates GUI elements when sensor disconnects or fails"""
        if not self.root.winfo_exists(): return # Check if window still exists
        self.euler_label.config(text="Euler: ---.--, ---.--, ---.--", fg="red")
        self.calib_label.config(text="Calib: S=-, G=-, A=-, M=-", fg="red")
        self.temp_label.config(text="Temp: --°C", fg="red")

    def on_closing(self):
        """Handles window close event"""
        print("Closing application...")
        self.sensor_running = False # Signal the thread to stop

        # Wait briefly for the thread to finish its current loop/close sensor
        if hasattr(self, 'sensor_thread') and self.sensor_thread.is_alive():
             self.sensor_thread.join(timeout=0.5) # Wait max 0.5 sec

        # Destroy the Tkinter window
        self.root.destroy()

# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    # Only start mainloop if sensor initialization didn't prevent app setup
    if hasattr(app, 'gl_frame'):
        root.mainloop()
    else:
        # If app init failed early (sensor error), keep the error window open
        print("Application did not start fully due to sensor issues.")
        if root.winfo_exists():
             root.mainloop()