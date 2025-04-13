from smbus2 import SMBus
from time import sleep
import json
import time
import tkinter as tk
from tkinter import ttk, Scale, Label, Button, Frame, StringVar
from enum import Enum

# PCA9685 constants
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

class ServoPositionLogger:
    def __init__(self, log_file="servo_positions.log"):
        self.log_file = log_file
        self.current_positions = {
            "armOne": {"angle": 0, "value": 0, "pulse_width": 0},
            "armTwo": {"angle": 0, "value": 0, "pulse_width": 0},
            "claw": {"angle": 0, "value": 0, "pulse_width": 0},
            "rotate": {"angle": 0, "value": 0, "pulse_width": 0}
        }
        # Initialize log file
        with open(self.log_file, 'w') as f:
            f.write("Servo Position Log - Started at: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            f.write("=" * 80 + "\n")
    
    def log_position(self, servo_name, angle, value, pulse_width):
        # Only log if there's actually a change
        if (self.current_positions[servo_name]["angle"] != angle or
            self.current_positions[servo_name]["value"] != value or
            self.current_positions[servo_name]["pulse_width"] != pulse_width):
            
            # Update current positions
            self.current_positions[servo_name]["angle"] = angle
            self.current_positions[servo_name]["value"] = value
            self.current_positions[servo_name]["pulse_width"] = pulse_width
            
            # Format the current time
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Create log message
            log_message = f"[{timestamp}] {servo_name:8} - Angle: {angle:6.2f}° | Value: {value:6.2f} | Pulse Width: {pulse_width:6.2f}µs"
            
            # Print to console
            print(log_message)
            
            # Write to file
            with open(self.log_file, 'a') as f:
                f.write(log_message + "\n")

class Servo:
    def __init__(self, channel, pca, min_pulse=900, max_pulse=2100, name="unnamed"):
        self.channel = channel
        self.pca = pca
        self.MIN_PULSE = min_pulse
        self.MAX_PULSE = max_pulse
        self.current_pulse = 1500  # Neutral position
        self.name = name
        self.last_angle = None  # To store the last angle for logging
        self.last_value = None  # To store the last value for logging
        
    def initialize(self):
        # Set to neutral position
        self._set_pulse_width(1500)
        sleep(0.5)
        print(f"Servo {self.name} on channel {self.channel} initialized")
        
    def set_value(self, value, angle=None):
        # Value is expected to be between -1 and 1 (like gpiozero)
        self.last_value = value
        
        if angle is None:
            # Calculate approximate angle if not provided
            angle = (value + 1) * 90  # Maps -1,1 to 0,180
        self.last_angle = angle
        
        pulse_width = self._map_value_to_pulse(value)
        self._set_pulse_width(pulse_width)
        
        # Log the position if a logger is available
        if hasattr(self, 'logger') and self.logger is not None:
            self.logger.log_position(self.name, angle, value, pulse_width)
        
    def set_angle(self, angle):
        """Set servo position directly using angle (0-180)"""
        value = angle_to_value(angle)
        self.set_value(value, angle)
        
    def _map_value_to_pulse(self, value):
        # Map value from -1,1 to pulse width
        value = max(-1.0, min(1.0, value))  # Ensure value is in range
        # Linear interpolation from -1,1 to min_pulse,max_pulse
        return self.MIN_PULSE + (value + 1) * (self.MAX_PULSE - self.MIN_PULSE) / 2
        
    def _set_pulse_width(self, pulse_width):
        duty_cycle = int((pulse_width / 20000.0) * 4096)
        self.pca.channels[self.channel].duty_cycle = duty_cycle
        print(f"Channel {self.channel} ({self.name}): pulse {pulse_width} µs -> duty_cycle {duty_cycle}")
        self.current_pulse = pulse_width
        time.sleep(0.001)  # Small delay to help register changes
        
    def set_logger(self, logger):
        self.logger = logger
        
    def set_pulse_width(self, pulse_width):
        """Set servo position directly using pulse width (in microseconds)"""
        self._set_pulse_width(pulse_width)
        # Calculate approximate value and angle
        value = (2 * (pulse_width - self.MIN_PULSE) / (self.MAX_PULSE - self.MIN_PULSE)) - 1
        angle = (value + 1) * 90
        # Log position if logger is available
        if hasattr(self, 'logger') and self.logger is not None:
            self.logger.log_position(self.name, angle, value, pulse_width)

def angle_to_value(angle):
    """Convert an angle (0-180°) to a servo value (-1 to 1)."""
    angle = max(0, min(180, angle))
    value = (angle / 90.0) - 1.0
    return max(-1.0, min(1.0, value))

class ServoCalibrator:
    def __init__(self, master, servos):
        self.master = master
        self.servos = servos
        
        master.title("Servo Calibrator")
        master.geometry("800x600")
        
        # Create notebook with tabs for different control modes
        self.notebook = ttk.Notebook(master)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create tabs
        self.angle_tab = Frame(self.notebook)
        self.value_tab = Frame(self.notebook)
        self.pulse_tab = Frame(self.notebook)
        self.presets_tab = Frame(self.notebook)
        
        self.notebook.add(self.angle_tab, text="Angle Control")
        self.notebook.add(self.value_tab, text="Value Control")
        self.notebook.add(self.pulse_tab, text="Pulse Width Control")
        self.notebook.add(self.presets_tab, text="Presets")
        
        # Setup each tab
        self.setup_angle_tab()
        self.setup_value_tab()
        self.setup_pulse_tab()
        self.setup_presets_tab()
        
        # Status bar at the bottom
        self.status_var = StringVar()
        self.status_var.set("Ready")
        self.status_bar = Label(master, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Create a main preset frame with save/load functionality
        self.saved_positions = {}
        
    def setup_angle_tab(self):
        # Create angle sliders for each servo
        Label(self.angle_tab, text="Control servos by angle (0-180°)", font=("Arial", 12)).pack(pady=10)
        
        # Create a frame for each servo
        for servo_name, servo in self.servos.items():
            frame = Frame(self.angle_tab)
            frame.pack(fill="x", padx=10, pady=5)
            
            Label(frame, text=f"{servo_name}:", width=10).pack(side="left")
            
            # Current value display
            value_var = StringVar()
            value_var.set("0°")
            value_label = Label(frame, textvariable=value_var, width=8)
            value_label.pack(side="right")
            
            # Slider for angle
            slider = Scale(frame, from_=0, to=180, orient="horizontal", 
                          command=lambda val, s=servo, v=value_var: self.on_angle_change(s, val, v))
            slider.set(90)  # Start at middle position
            slider.pack(side="left", fill="x", expand=True)
            
    def setup_value_tab(self):
        # Create value sliders for each servo (-1 to 1)
        Label(self.value_tab, text="Control servos by value (-1 to 1)", font=("Arial", 12)).pack(pady=10)
        
        # Create a frame for each servo
        for servo_name, servo in self.servos.items():
            frame = Frame(self.value_tab)
            frame.pack(fill="x", padx=10, pady=5)
            
            Label(frame, text=f"{servo_name}:", width=10).pack(side="left")
            
            # Current value display
            value_var = StringVar()
            value_var.set("0.0")
            value_label = Label(frame, textvariable=value_var, width=8)
            value_label.pack(side="right")
            
            # Slider for value
            slider = Scale(frame, from_=-100, to=100, orient="horizontal",
                          command=lambda val, s=servo, v=value_var: self.on_value_change(s, val, v))
            slider.set(0)  # Start at middle position
            slider.pack(side="left", fill="x", expand=True)
            
    def setup_pulse_tab(self):
        # Create pulse width sliders for each servo
        Label(self.pulse_tab, text="Control servos by pulse width (µs)", font=("Arial", 12)).pack(pady=10)
        
        # Create a frame for each servo
        for servo_name, servo in self.servos.items():
            frame = Frame(self.pulse_tab)
            frame.pack(fill="x", padx=10, pady=5)
            
            Label(frame, text=f"{servo_name}:", width=10).pack(side="left")
            
            # Current value display
            value_var = StringVar()
            value_var.set("1500 µs")
            value_label = Label(frame, textvariable=value_var, width=10)
            value_label.pack(side="right")
            
            # Slider for pulse width
            slider = Scale(frame, from_=500, to=2500, orient="horizontal", 
                          command=lambda val, s=servo, v=value_var: self.on_pulse_change(s, val, v))
            slider.set(1500)  # Start at neutral
            slider.pack(side="left", fill="x", expand=True)
    
    def setup_presets_tab(self):
        Label(self.presets_tab, text="Preset Positions", font=("Arial", 12)).pack(pady=10)
        
        # Create frame for buttons
        button_frame = Frame(self.presets_tab)
        button_frame.pack(fill="x", padx=10, pady=5)
        
        # Neutral position button
        Button(button_frame, text="Neutral", command=self.set_neutral).pack(side="left", padx=5)
        
        # Predefined positions (can be adjusted as needed)
        pos1_btn = Button(button_frame, text="ARM_ONE_FWD", 
                         command=lambda: self.set_preset_position("ARM_ONE_FWD"))
        pos1_btn.pack(side="left", padx=5)
        
        pos2_btn = Button(button_frame, text="ARM_ONE_DWN", 
                         command=lambda: self.set_preset_position("ARM_ONE_DWN"))
        pos2_btn.pack(side="left", padx=5)
        
        pos3_btn = Button(button_frame, text="CLAW_OPEN", 
                         command=lambda: self.set_preset_position("CLAW_OPEN"))
        pos3_btn.pack(side="left", padx=5)
        
        pos4_btn = Button(button_frame, text="CLAW_CLOSED", 
                         command=lambda: self.set_preset_position("CLAW_CLOSED"))
        pos4_btn.pack(side="left", padx=5)
        
        # Frame for saving positions
        save_frame = Frame(self.presets_tab)
        save_frame.pack(fill="x", padx=10, pady=20)
        
        Label(save_frame, text="Position Name:").pack(side="left")
        self.preset_name_var = StringVar()
        name_entry = ttk.Entry(save_frame, textvariable=self.preset_name_var, width=20)
        name_entry.pack(side="left", padx=5)
        
        save_btn = Button(save_frame, text="Save Current Position", command=self.save_position)
        save_btn.pack(side="left", padx=5)
        
        # Frame for displaying saved positions
        self.saved_positions_frame = Frame(self.presets_tab)
        self.saved_positions_frame.pack(fill="both", expand=True, padx=10, pady=5)
        Label(self.saved_positions_frame, text="Saved Positions:").pack(anchor="w")
        
        # Export/import buttons
        export_frame = Frame(self.presets_tab)
        export_frame.pack(fill="x", padx=10, pady=5)
        Button(export_frame, text="Export Positions", command=self.export_positions).pack(side="left", padx=5)
        Button(export_frame, text="Import Positions", command=self.import_positions).pack(side="left", padx=5)
    
    def on_angle_change(self, servo, angle, value_var):
        angle = float(angle)
        servo.set_angle(angle)
        value_var.set(f"{angle:.1f}°")
        
    def on_value_change(self, servo, scaled_value, value_var):
        # Convert slider value (-100 to 100) to servo value (-1 to 1)
        value = float(scaled_value) / 100.0
        servo.set_value(value)
        value_var.set(f"{value:.2f}")
        
    def on_pulse_change(self, servo, pulse, value_var):
        pulse = int(pulse)
        servo.set_pulse_width(pulse)
        value_var.set(f"{pulse} µs")
        
    def set_neutral(self):
        """Set all servos to neutral position"""
        for servo in self.servos.values():
            servo.set_pulse_width(1500)
        self.status_var.set("All servos set to neutral position")
        
    def set_preset_position(self, preset_name):
        """Set predefined positions"""
        if preset_name == "ARM_ONE_FWD":
            self.servos["armOne"].set_angle(45)
            self.status_var.set(f"Set armOne to {preset_name} position (45°)")
        elif preset_name == "ARM_ONE_DWN":
            self.servos["armOne"].set_angle(90)
            self.status_var.set(f"Set armOne to {preset_name} position (90°)")
        elif preset_name == "CLAW_OPEN":
            self.servos["claw"].set_angle(180)
            self.status_var.set(f"Set claw to {preset_name} position (180°)")
        elif preset_name == "CLAW_CLOSED":
            self.servos["claw"].set_angle(90)
            self.status_var.set(f"Set claw to {preset_name} position (90°)")
        elif preset_name in self.saved_positions:
            # Load custom saved position
            position = self.saved_positions[preset_name]
            for servo_name, values in position.items():
                if servo_name in self.servos:
                    self.servos[servo_name].set_pulse_width(values["pulse_width"])
            self.status_var.set(f"Loaded saved position: {preset_name}")
            
    def save_position(self):
        """Save current servo positions as a preset"""
        name = self.preset_name_var.get().strip()
        if not name:
            self.status_var.set("Please enter a name for the position")
            return
            
        # Save all servo positions
        position = {}
        for servo_name, servo in self.servos.items():
            position[servo_name] = {
                "angle": servo.last_angle,
                "value": servo.last_value,
                "pulse_width": servo.current_pulse
            }
            
        self.saved_positions[name] = position
        self.status_var.set(f"Position '{name}' saved")
        self.update_saved_positions_display()
        
        # Clear the entry field
        self.preset_name_var.set("")
        
    def update_saved_positions_display(self):
        """Update the display of saved positions"""
        # Clear existing buttons
        for widget in self.saved_positions_frame.winfo_children()[1:]:
            widget.destroy()
            
        # Create a button for each saved position
        if not self.saved_positions:
            Label(self.saved_positions_frame, text="No positions saved yet").pack(anchor="w")
        else:
            positions_frame = Frame(self.saved_positions_frame)
            positions_frame.pack(fill="both", expand=True)
            
            row = 0
            col = 0
            for name in self.saved_positions.keys():
                Button(positions_frame, text=name, 
                      command=lambda n=name: self.set_preset_position(n)).grid(row=row, column=col, padx=5, pady=5)
                col += 1
                if col > 4:  # Wrap after 5 buttons per row
                    col = 0
                    row += 1
    
    def export_positions(self):
        """Export saved positions to a JSON file"""
        try:
            with open("servo_positions.json", "w") as f:
                json.dump(self.saved_positions, f, indent=2)
            self.status_var.set("Positions exported to servo_positions.json")
        except Exception as e:
            self.status_var.set(f"Error exporting positions: {e}")
    
    def import_positions(self):
        """Import saved positions from a JSON file"""
        try:
            with open("servo_positions.json", "r") as f:
                self.saved_positions = json.load(f)
            self.update_saved_positions_display()
            self.status_var.set("Positions imported from servo_positions.json")
        except FileNotFoundError:
            self.status_var.set("File servo_positions.json not found")
        except Exception as e:
            self.status_var.set(f"Error importing positions: {e}")

def main():
    # Initialize the PCA9685 driver
    pca = PCA9685(bus_number=7)
    pca.frequency = 50  # Standard frequency for servos and ESCs
    
    # Create a position logger
    position_logger = ServoPositionLogger()
    
    # Initialize servos
    servos = {
        "armOne": Servo(0, pca, min_pulse=900, max_pulse=2100, name="armOne"), #claw //500 - rest 2100 close fully
        "armTwo": Servo(1, pca, min_pulse=900, max_pulse=2100, name="armTwo"), #rorate  //500 rest 1450 ish is vertical 2000
        "claw": Servo(2, pca, min_pulse=900, max_pulse=2100, name="claw"), #arm2  //850 max up 1250 straight out 1600 down
        "rotate": Servo(3, pca, min_pulse=900, max_pulse=2100, name="rotate") #arm1  //900 hidden away 1125 straight down 1600 straight out
    }
    
    # Add logger to each servo
    for servo_name, servo in servos.items():
        servo.set_logger(position_logger)
    
    # Initialize all servos
    for servo_name, servo in servos.items():
        servo.initialize()
    
    # Create the Tkinter application
    root = tk.Tk()
    app = ServoCalibrator(root, servos)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Application terminated by user")
    finally:
        # Set all servos to neutral position and close the bus
        for servo in servos.values():
            servo.set_pulse_width(1500)
        pca.deinit()
        print("PCA9685 bus closed")

if __name__ == '__main__':
    main()