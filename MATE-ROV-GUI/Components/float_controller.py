import requests
import json
import traceback
import os
import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                            QLineEdit, QTableWidget, QTableWidgetItem, QFormLayout, 
                            QGroupBox, QTabWidget, QDoubleSpinBox, QSpinBox, QMessageBox,
                            QHeaderView, QFileDialog, QCheckBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import socket

# Set the plotly renderer to browser for display
pio.renderers.default = "browser"

class FloatStatusWorker(QThread):
    """Worker thread to fetch float status without blocking the UI"""
    status_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, ip_address):
        super().__init__()
        self.ip_address = ip_address
        self.running = True
        
    def run(self):
        while self.running:
            try:
                url = f"http://{self.ip_address}/status"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    self.status_received.emit(response.json())
                else:
                    self.error_occurred.emit(f"Error: Server returned status code {response.status_code}")
            except Exception as e:
                self.error_occurred.emit(f"Connection error: {str(e)}")
            
            # Sleep for 2 seconds before polling again
            self.msleep(2000)
            
    def stop(self):
        self.running = False
        self.wait()

class FloatController(QWidget):
    """Widget for controlling and monitoring the MATE ROV Float"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.float_ip = ""
        self.data_directory = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'float_data')
        if not os.path.exists(self.data_directory):
            os.makedirs(self.data_directory)
        
        # Initialize data capture state
        self.capturing_data = False
        self.capture_start_time = None
        self.current_capture_file = None
        
        # Track if fields are being edited
        self.editing_fields = False
        self.auto_update_timer = QTimer()
        self.auto_update_timer.timeout.connect(self.update_parameter_fields)
        self.auto_update_timer.start(10000)  # 10 second delay for auto-updating fields
        
        self.setupUI()
        
    def setupUI(self):
        """Create the user interface"""
        main_layout = QVBoxLayout()
        
        # IP Configuration
        ip_layout = QHBoxLayout()
        ip_label = QLabel("Float IP:")
        self.ip_input = QLineEdit("192.168.1.226")  # Default IP
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.connect_to_float)
        
        ip_layout.addWidget(ip_label)
        ip_layout.addWidget(self.ip_input)
        ip_layout.addWidget(connect_btn)
        
        main_layout.addLayout(ip_layout)
        
        # Tabs for different sections
        tabs = QTabWidget()
        
        # Status tab
        status_tab = QWidget()
        status_layout = QVBoxLayout()
        
        # Status table
        self.status_table = QTableWidget(0, 2)
        self.status_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.status_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.status_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.status_table.verticalHeader().setVisible(False)
        status_layout.addWidget(self.status_table)
        
        # Manual refresh button
        refresh_btn = QPushButton("Refresh Status")
        refresh_btn.clicked.connect(self.manual_refresh)
        status_layout.addWidget(refresh_btn)
        
        status_tab.setLayout(status_layout)
        tabs.addTab(status_tab, "Status")
        
        # Controls tab
        control_tab = QWidget()
        control_layout = QVBoxLayout()
        
        # Basic controls
        basic_group = QGroupBox("Basic Controls")
        basic_layout = QHBoxLayout()
        
        # Start/Stop buttons
        start_btn = QPushButton("Start Float")
        start_btn.clicked.connect(lambda: self.send_command("s"))
        
        vel_test_start_btn = QPushButton("Start Velocity Test")
        vel_test_start_btn.clicked.connect(lambda: self.send_command("vs"))
        
        vel_test_stop_btn = QPushButton("Stop Velocity Test")
        vel_test_stop_btn.clicked.connect(lambda: self.send_command("vst"))
        
        stop_btn = QPushButton("Stop Float")
        stop_btn.clicked.connect(lambda: self.send_command("st"))
        
        start_routine_btn = QPushButton("Start Routine")
        start_routine_btn.clicked.connect(lambda: self.send_command("rs"))
        
        basic_layout.addWidget(start_btn)
        basic_layout.addWidget(vel_test_start_btn)
        basic_layout.addWidget(vel_test_stop_btn)
        basic_layout.addWidget(stop_btn)
        basic_layout.addWidget(start_routine_btn)
        
        basic_group.setLayout(basic_layout)
        control_layout.addWidget(basic_group)
        
        # Pump controls
        pump_group = QGroupBox("Pump Controls")
        pump_layout = QHBoxLayout()
        
        ascend_btn = QPushButton("Ascend")
        ascend_btn.clicked.connect(lambda: self.send_command("a"))
        
        descend_btn = QPushButton("Descend")
        descend_btn.clicked.connect(lambda: self.send_command("d"))
        
        pump_stop_btn = QPushButton("Stop Pump")
        pump_stop_btn.clicked.connect(lambda: self.send_command("."))
        
        pump_layout.addWidget(ascend_btn)
        pump_layout.addWidget(descend_btn)
        pump_layout.addWidget(pump_stop_btn)
        
        pump_group.setLayout(pump_layout)
        control_layout.addWidget(pump_group)
        
        # PID Toggle
        pid_toggle_btn = QPushButton("Toggle PID Control")
        pid_toggle_btn.clicked.connect(lambda: self.send_command("pid_toggle"))
        control_layout.addWidget(pid_toggle_btn)
        
        # Data Capture Controls
        capture_group = QGroupBox("Data Capture")
        capture_layout = QVBoxLayout()
        
        capture_btn_layout = QHBoxLayout()
        self.start_capture_btn = QPushButton("Start New Capture")
        self.start_capture_btn.clicked.connect(self.start_new_capture)
        
        self.stop_capture_btn = QPushButton("Stop Capture")
        self.stop_capture_btn.clicked.connect(self.stop_capture)
        self.stop_capture_btn.setEnabled(False)
        
        capture_btn_layout.addWidget(self.start_capture_btn)
        capture_btn_layout.addWidget(self.stop_capture_btn)
        
        self.capture_status_label = QLabel("Data capture not active")
        
        capture_layout.addLayout(capture_btn_layout)
        capture_layout.addWidget(self.capture_status_label)
        
        capture_group.setLayout(capture_layout)
        control_layout.addWidget(capture_group)
        
        control_tab.setLayout(control_layout)
        tabs.addTab(control_tab, "Controls")
        
        # Parameters tab
        param_tab = QWidget()
        param_layout = QVBoxLayout()
        
        # Auto-update control
        auto_update_layout = QHBoxLayout()
        self.auto_update_checkbox = QCheckBox("Auto-update parameters")
        self.auto_update_checkbox.setChecked(True)
        self.auto_update_checkbox.stateChanged.connect(self.toggle_auto_update)
        
        auto_update_layout.addWidget(self.auto_update_checkbox)
        auto_update_layout.addStretch()
        
        # Manual update button
        manual_update_btn = QPushButton("Update Parameter Fields")
        manual_update_btn.clicked.connect(self.update_parameter_fields)
        auto_update_layout.addWidget(manual_update_btn)
        
        param_layout.addLayout(auto_update_layout)
        
        # PID Parameters
        pid_group = QGroupBox("PID Parameters")
        pid_form = QFormLayout()
        
        self.kp_input = QDoubleSpinBox()
        self.kp_input.setRange(0, 100)
        self.kp_input.setDecimals(3)
        self.kp_input.setSingleStep(0.1)
        self.kp_input.valueChanged.connect(self.parameter_editing_started)
        
        self.ki_input = QDoubleSpinBox()
        self.ki_input.setRange(0, 100)
        self.ki_input.setDecimals(3)
        self.ki_input.setSingleStep(0.01)
        self.ki_input.valueChanged.connect(self.parameter_editing_started)
        
        self.kd_input = QDoubleSpinBox()
        self.kd_input.setRange(0, 100)
        self.kd_input.setDecimals(3)
        self.kd_input.setSingleStep(0.01)
        self.kd_input.valueChanged.connect(self.parameter_editing_started)
        
        self.deadband_input = QSpinBox()
        self.deadband_input.setRange(0, 50)
        self.deadband_input.setSingleStep(1)
        self.deadband_input.valueChanged.connect(self.parameter_editing_started)
        
        pid_form.addRow("Kp:", self.kp_input)
        pid_form.addRow("Ki:", self.ki_input)
        pid_form.addRow("Kd:", self.kd_input)
        pid_form.addRow("Deadband:", self.deadband_input)
        
        set_pid_btn = QPushButton("Set PID Parameters")
        set_pid_btn.clicked.connect(self.set_pid_params)
        
        set_deadband_btn = QPushButton("Set Deadband")
        set_deadband_btn.clicked.connect(self.set_pid_deadband)
        
        pid_buttons_layout = QHBoxLayout()
        pid_buttons_layout.addWidget(set_pid_btn)
        pid_buttons_layout.addWidget(set_deadband_btn)
        
        pid_group.setLayout(pid_form)
        param_layout.addWidget(pid_group)
        param_layout.addLayout(pid_buttons_layout)
        
        # Velocity limits
        vel_group = QGroupBox("Velocity Limits")
        vel_form = QFormLayout()
        
        self.descent_vel_input = QDoubleSpinBox()
        self.descent_vel_input.setRange(0, 1)
        self.descent_vel_input.setDecimals(3)
        self.descent_vel_input.setSingleStep(0.01)
        self.descent_vel_input.valueChanged.connect(self.parameter_editing_started)
        
        self.ascent_vel_input = QDoubleSpinBox()
        self.ascent_vel_input.setRange(0, 1)
        self.ascent_vel_input.setDecimals(3)
        self.ascent_vel_input.setSingleStep(0.01)
        self.ascent_vel_input.valueChanged.connect(self.parameter_editing_started)
        
        vel_form.addRow("Max Descent (m/s):", self.descent_vel_input)
        vel_form.addRow("Max Ascent (m/s):", self.ascent_vel_input)
        
        set_vel_btn = QPushButton("Set Velocity Limits")
        set_vel_btn.clicked.connect(self.set_velocity_limits)
        
        vel_group.setLayout(vel_form)
        param_layout.addWidget(vel_group)
        param_layout.addWidget(set_vel_btn)
        
        # Target Depth
        depth_group = QGroupBox("Target Depth")
        depth_form = QFormLayout()
        
        self.target_depth_input = QDoubleSpinBox()
        self.target_depth_input.setRange(0, 10)
        self.target_depth_input.setDecimals(3)
        self.target_depth_input.setSingleStep(0.1)
        self.target_depth_input.valueChanged.connect(self.parameter_editing_started)
        
        self.depth_tolerance_input = QDoubleSpinBox()
        self.depth_tolerance_input.setRange(0.01, 1.0)
        self.depth_tolerance_input.setDecimals(3)
        self.depth_tolerance_input.setSingleStep(0.01)
        self.depth_tolerance_input.valueChanged.connect(self.parameter_editing_started)
        
        depth_form.addRow("Target Depth (m):", self.target_depth_input)
        depth_form.addRow("Tolerance (±m):", self.depth_tolerance_input)
        
        depth_buttons_layout = QHBoxLayout()
        
        set_depth_btn = QPushButton("Set Target Depth")
        set_depth_btn.clicked.connect(self.set_target_depth)
        
        set_tolerance_btn = QPushButton("Set Tolerance")
        set_tolerance_btn.clicked.connect(self.set_depth_tolerance)
        
        depth_buttons_layout.addWidget(set_depth_btn)
        depth_buttons_layout.addWidget(set_tolerance_btn)
        
        depth_group.setLayout(depth_form)
        param_layout.addWidget(depth_group)
        param_layout.addLayout(depth_buttons_layout)
        
        # Wait Time
        wait_group = QGroupBox("Routine Wait Time")
        wait_form = QFormLayout()
        
        self.wait_time_input = QSpinBox()
        self.wait_time_input.setRange(1, 300)
        self.wait_time_input.setSingleStep(1)
        self.wait_time_input.valueChanged.connect(self.parameter_editing_started)
        
        wait_form.addRow("Wait Time (seconds):", self.wait_time_input)
        
        set_wait_btn = QPushButton("Set Wait Time")
        set_wait_btn.clicked.connect(self.set_wait_time)
        
        wait_group.setLayout(wait_form)
        param_layout.addWidget(wait_group)
        param_layout.addWidget(set_wait_btn)
        
        # Read Interval
        interval_group = QGroupBox("Data Read Intervals")
        interval_form = QFormLayout()
        
        self.normal_interval_input = QSpinBox()
        self.normal_interval_input.setRange(100, 10000)
        self.normal_interval_input.setSingleStep(100)
        self.normal_interval_input.valueChanged.connect(self.parameter_editing_started)
        
        self.velocity_interval_input = QSpinBox()
        self.velocity_interval_input.setRange(10, 1000)
        self.velocity_interval_input.setSingleStep(10)
        self.velocity_interval_input.valueChanged.connect(self.parameter_editing_started)
        
        interval_form.addRow("Normal Interval (ms):", self.normal_interval_input)
        interval_form.addRow("Velocity Interval (ms):", self.velocity_interval_input)
        
        set_interval_btn = QPushButton("Set Intervals")
        set_interval_btn.clicked.connect(self.set_read_intervals)
        
        interval_group.setLayout(interval_form)
        param_layout.addWidget(interval_group)
        param_layout.addWidget(set_interval_btn)
        
        # Company settings
        company_group = QGroupBox("Company Settings")
        company_form = QFormLayout()

        self.company_number_input = QSpinBox()
        self.company_number_input.setRange(1, 99999)
        self.company_number_input.setSingleStep(1)
        self.company_number_input.valueChanged.connect(self.parameter_editing_started)

        company_form.addRow("Company Number:", self.company_number_input)

        set_company_btn = QPushButton("Set Company Number")
        set_company_btn.clicked.connect(self.set_company_number)

        company_group.setLayout(company_form)
        param_layout.addWidget(company_group)
        param_layout.addWidget(set_company_btn)

        param_tab.setLayout(param_layout)
        tabs.addTab(param_tab, "Parameters")
        
        # Graph tab
        graph_tab = QWidget()
        graph_layout = QVBoxLayout()
        
        graph_actions_layout = QHBoxLayout()
        
        plot_depth_btn = QPushButton("Plot Depth Graph")
        plot_depth_btn.clicked.connect(self.plot_depth_data)
        
        save_data_btn = QPushButton("Save Current Data")
        save_data_btn.clicked.connect(self.save_current_data)
        
        load_data_btn = QPushButton("Load and Plot Data...")
        load_data_btn.clicked.connect(self.load_and_plot_data)
        
        graph_actions_layout.addWidget(plot_depth_btn)
        graph_actions_layout.addWidget(save_data_btn)
        graph_actions_layout.addWidget(load_data_btn)
        
        graph_layout.addLayout(graph_actions_layout)
        
        graph_description = QLabel("Click 'Plot Depth Graph' to visualize the depth data from the float. " 
                                  "The graph will show depth over time, velocity, PID output, and PID error. "
                                  "Use 'Start New Capture' in the Controls tab to begin a fresh data collection.")
        graph_description.setWordWrap(True)
        graph_layout.addWidget(graph_description)
        
        # Saved data info
        saved_data_group = QGroupBox("Saved Data")
        saved_data_layout = QVBoxLayout()
        
        self.saved_data_label = QLabel("No data saved yet")
        self.saved_data_label.setAlignment(Qt.AlignCenter)
        saved_data_layout.addWidget(self.saved_data_label)
        
        saved_data_group.setLayout(saved_data_layout)
        graph_layout.addWidget(saved_data_group)
        
        graph_tab.setLayout(graph_layout)
        tabs.addTab(graph_tab, "Graph")
        
        main_layout.addWidget(tabs)
        
        self.setLayout(main_layout)
        
        # Initialize status data
        self.latest_status_data = {}
        self.depth_data = []
        
        # Update saved data info
        self.update_saved_data_info()

        # Dashboard tab
        dashboard_tab = QWidget()
        dashboard_layout = QVBoxLayout()

        # Company information
        company_group = QGroupBox("Company Information")
        company_layout = QFormLayout()

        # Static company name
        company_name_label = QLabel("SBRT")
        company_name_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        # Dynamic company number
        self.company_number_label = QLabel("--")
        self.company_number_label.setStyleSheet("font-size: 16px;")

        company_layout.addRow("Company Name:", company_name_label)
        company_layout.addRow("Company Number:", self.company_number_label)

        company_group.setLayout(company_layout)
        dashboard_layout.addWidget(company_group)

        # Time information
        time_group = QGroupBox("Time Information")
        time_layout = QFormLayout()

        self.float_time_label = QLabel("--")
        self.float_time_label.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.float_uptime_label = QLabel("--")
        self.local_time_label = QLabel("--")

        time_layout.addRow("Float Time (s):", self.float_time_label)
        time_layout.addRow("Float Uptime:", self.float_uptime_label)
        time_layout.addRow("Local Time:", self.local_time_label)

        time_group.setLayout(time_layout)
        dashboard_layout.addWidget(time_group)

        # Depth and pressure information
        depth_group = QGroupBox("Depth and Pressure")
        depth_layout = QFormLayout()

        self.current_depth_label = QLabel("--")
        self.current_depth_label.setStyleSheet("font-size: 24px; font-weight: bold;")

        self.current_pressure_label = QLabel("--")
        self.current_pressure_label.setStyleSheet("font-size: 18px;")

        self.target_depth_label = QLabel("--")
        self.depth_error_label = QLabel("--")

        depth_layout.addRow("Current Depth:", self.current_depth_label)
        depth_layout.addRow("Current Pressure:", self.current_pressure_label)
        depth_layout.addRow("Target Depth:", self.target_depth_label)
        depth_layout.addRow("Depth Error:", self.depth_error_label)

        depth_group.setLayout(depth_layout)
        dashboard_layout.addWidget(depth_group)

        # Status information
        status_group = QGroupBox("System Status")
        status_layout = QFormLayout()

        self.pump_status_label = QLabel("--")
        self.pid_status_label = QLabel("--")
        self.routine_status_label = QLabel("--")
        self.wifi_status_label = QLabel("--")

        status_layout.addRow("Pump:", self.pump_status_label)
        status_layout.addRow("PID Control:", self.pid_status_label)
        status_layout.addRow("Routine:", self.routine_status_label)
        status_layout.addRow("WiFi Signal:", self.wifi_status_label)

        status_group.setLayout(status_layout)
        dashboard_layout.addWidget(status_group)

        # Setup timer for local time updates
        self.local_time_timer = QTimer()
        self.local_time_timer.timeout.connect(self.update_local_time)
        self.local_time_timer.start(1000)  # Update every second

        dashboard_tab.setLayout(dashboard_layout)
        tabs.addTab(dashboard_tab, "Dashboard")
    
    def parameter_editing_started(self):
        """Called when the user starts editing a parameter field"""
        self.editing_fields = True
        # Reset the auto-update timer
        if self.auto_update_checkbox.isChecked():
            self.auto_update_timer.start(10000)  # 10 second delay
    
    def toggle_auto_update(self, state):
        """Toggle automatic parameter field updates"""
        if state == Qt.Checked:
            self.auto_update_timer.start(10000)
        else:
            self.auto_update_timer.stop()
    
    def start_new_capture(self):
        """Start a new data capture session"""
        self.depth_data = []  # Clear existing data
        self.capturing_data = True
        self.capture_start_time = datetime.datetime.now()
        
        # Create a new capture file name
        timestamp = self.capture_start_time.strftime("%Y%m%d_%H%M%S")
        self.current_capture_file = f"float_capture_{timestamp}.json"
        
        # Update UI
        self.start_capture_btn.setEnabled(False)
        self.stop_capture_btn.setEnabled(True)
        self.capture_status_label.setText(f"Capturing data to {self.current_capture_file}")
        
        # Inform the user
        QMessageBox.information(self, "Data Capture Started", 
                               f"Started a new data capture session.\nData will be saved to {self.current_capture_file}")
    
    def stop_capture(self):
        """Stop the current data capture and save it"""
        if not self.capturing_data:
            return
            
        self.capturing_data = False
        
        # Save the captured data
        if self.depth_data and self.current_capture_file:
            filepath = os.path.join(self.data_directory, self.current_capture_file)
            
            try:
                with open(filepath, 'w') as f:
                    json.dump(self.depth_data, f, indent=2)
                
                # Also save to coordinates_data.json
                self.save_to_coordinates_json(self.depth_data)
                
                # Update UI
                self.start_capture_btn.setEnabled(True)
                self.stop_capture_btn.setEnabled(False)
                self.capture_status_label.setText(f"Capture stopped. Saved {len(self.depth_data)} data points.")
                
                # Update saved data info
                self.update_saved_data_info()
                
                # Inform the user
                QMessageBox.information(self, "Data Capture Completed", 
                                      f"Capture completed. Saved {len(self.depth_data)} data points to {self.current_capture_file}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Error saving capture data: {str(e)}")
                traceback.print_exc()
        else:
            self.start_capture_btn.setEnabled(True)
            self.stop_capture_btn.setEnabled(False)
            self.capture_status_label.setText("Capture stopped. No data to save.")
    
    def connect_to_float(self):
        """Connect to the float and start polling for status"""
        self.float_ip = self.ip_input.text().strip()
        
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please enter a valid IP address")
            return
            
        # Stop any existing worker
        if self.worker:
            self.worker.stop()
            
        # Create a new worker
        self.worker = FloatStatusWorker(self.float_ip)
        self.worker.status_received.connect(self.update_status)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.start()
        
        # Immediate status request
        self.manual_refresh()
        
    def manual_refresh(self):
        """Manually refresh the status data"""
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first")
            return
            
        try:
            url = f"http://{self.float_ip}/status"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                self.update_status(response.json())
            else:
                self.handle_error(f"Error: Server returned status code {response.status_code}")
        except Exception as e:
            self.handle_error(f"Connection error: {str(e)}")
    
    def update_status(self, status_data):
        """Update the status table with the received data"""
        self.latest_status_data = status_data
        self.status_table.setRowCount(0)  # Clear existing rows
        
        # Flatten the nested structure for display
        flat_data = self.flatten_dict(status_data)
        
        # Fill the table
        for i, (key, value) in enumerate(flat_data.items()):
            self.status_table.insertRow(i)
            self.status_table.setItem(i, 0, QTableWidgetItem(key))
            self.status_table.setItem(i, 1, QTableWidgetItem(str(value)))
        
        # Update dashboard with the new data
        self.update_dashboard(status_data)
        
        # Update parameter fields if auto-update is enabled and not currently editing
        if self.auto_update_checkbox.isChecked() and not self.editing_fields:
            self.update_parameter_fields()
        
        # Reset editing flag after a short delay if it was set
        if self.editing_fields:
            QTimer.singleShot(10000, self.reset_editing_flag)
                
        # Store depth data for plotting if we're capturing
        if self.capturing_data and 'depth' in status_data and 'current' in status_data['depth']:
            try:
                data_point = {
                    'time': status_data['uptime_seconds'],
                    'depth': status_data['depth']['current'],
                    'pressure': status_data['depth']['pressure'] if 'pressure' in status_data['depth'] else 0,
                    'velocity': status_data['velocity']['current'] if 'velocity' in status_data and 'current' in status_data['velocity'] else 0,
                    'pid_output': status_data['pid']['last_output'] if 'pid' in status_data and 'last_output' in status_data['pid'] else 0,
                    'pid_error': status_data['pid']['last_error'] if 'pid' in status_data and 'last_error' in status_data['pid'] else 0,
                    'pump_status': status_data['pump']['state'] if 'pump' in status_data and 'state' in status_data['pump'] else 'unknown'
                }
                self.depth_data.append(data_point)
                
                # Periodically save the ongoing capture data
                if len(self.depth_data) % 20 == 0 and self.current_capture_file:
                    try:
                        filepath = os.path.join(self.data_directory, self.current_capture_file)
                        with open(filepath, 'w') as f:
                            json.dump(self.depth_data, f, indent=2)
                        self.capture_status_label.setText(f"Capturing: {len(self.depth_data)} points recorded")
                    except Exception as e:
                        print(f"Error auto-saving capture: {e}")
            except Exception as e:
                print(f"Error storing depth data: {e}")
                traceback.print_exc()

    def update_local_time(self):
        """Update the local time display"""
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.local_time_label.setText(current_time)

    def update_dashboard(self, status_data):
        """Update the dashboard with the latest status data"""
        if not status_data:
            return
            
        # Update company number - directly from status data or use constant
        if 'company_number' in status_data:
            # Get it from the status response
            company_number = status_data['company_number']
            self.company_number_label.setText(str(company_number))

        # Update time information
        if 'uptime_seconds' in status_data:
            uptime_seconds = status_data['uptime_seconds']
            self.float_time_label.setText(f"{uptime_seconds:.1f} s")
            
            # Format uptime into hours:minutes:seconds
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.float_uptime_label.setText(f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}")
        
        # Update depth and pressure information
        if 'depth' in status_data:
            depth_data = status_data['depth']
            if 'current' in depth_data:
                self.current_depth_label.setText(f"{depth_data['current']:.3f} m")
            if 'pressure' in depth_data:
                self.current_pressure_label.setText(f"{depth_data['pressure']:.2f} mbar")
            if 'target' in depth_data:
                self.target_depth_label.setText(f"{depth_data['target']:.3f} m")
        
        # Update depth error
        if 'pid' in status_data and 'last_error' in status_data['pid']:
            error = status_data['pid']['last_error']
            self.depth_error_label.setText(f"{error:.3f} m")
            
            # Set color based on error
            if abs(error) < 0.05:
                self.depth_error_label.setStyleSheet("color: green; font-weight: bold;")
            elif abs(error) < 0.1:
                self.depth_error_label.setStyleSheet("color: orange; font-weight: bold;")
            else:
                self.depth_error_label.setStyleSheet("color: red; font-weight: bold;")
        
        # Update system status
        if 'pump' in status_data and 'state' in status_data['pump']:
            pump_state = status_data['pump']['state']
            self.pump_status_label.setText(pump_state.capitalize())
            
            # Set color based on pump state
            if pump_state == "off":
                self.pump_status_label.setStyleSheet("color: gray;")
            elif pump_state == "ascending":
                self.pump_status_label.setStyleSheet("color: blue; font-weight: bold;")
            elif pump_state == "descending":
                self.pump_status_label.setStyleSheet("color: red; font-weight: bold;")
        
        if 'pid' in status_data and 'active' in status_data['pid']:
            pid_active = status_data['pid']['active']
            self.pid_status_label.setText("Active" if pid_active else "Inactive")
            self.pid_status_label.setStyleSheet("color: green; font-weight: bold;" if pid_active else "color: gray;")
        
        if 'routine' in status_data:
            routine_data = status_data['routine']
            if 'active' in routine_data and routine_data['active']:
                if 'state' in routine_data:
                    state = routine_data['state']
                    if state == "waiting" and 'wait_remaining_seconds' in routine_data:
                        self.routine_status_label.setText(f"Active: {state.capitalize()} ({routine_data['wait_remaining_seconds']}s)")
                    else:
                        self.routine_status_label.setText(f"Active: {state.capitalize()}")
                    self.routine_status_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.routine_status_label.setText("Inactive")
                self.routine_status_label.setStyleSheet("color: gray;")
        
        if 'wifi' in status_data:
            wifi_data = status_data['wifi']
            if 'rssi' in wifi_data and 'good_signal' in wifi_data:
                rssi = wifi_data['rssi']
                good_signal = wifi_data['good_signal']
                self.wifi_status_label.setText(f"{rssi} dBm ({'Good' if good_signal else 'Poor'})")
                self.wifi_status_label.setStyleSheet("color: green; font-weight: bold;" if good_signal else "color: red; font-weight: bold;")
    def update_parameter_fields(self):
        """Update parameter input fields with current values from status data"""
        if not self.latest_status_data:
            return
            
        try:
            # Store current values to detect changes
            old_values = {
                'kp': self.kp_input.value(),
                'ki': self.ki_input.value(),
                'kd': self.kd_input.value(),
                'deadband': self.deadband_input.value(),
                'descent_vel': self.descent_vel_input.value(),
                'ascent_vel': self.ascent_vel_input.value(),
                'target_depth': self.target_depth_input.value(),
                'tolerance': self.depth_tolerance_input.value(),
                'wait_time': self.wait_time_input.value(),
                'normal_interval': self.normal_interval_input.value(),
                'velocity_interval': self.velocity_interval_input.value(),
                'company_number': self.company_number_input.value()  # Add this line
            }
            # Update company number if it exists in status data
            if 'company_number' in self.latest_status_data:
                self.company_number_input.setValue(self.latest_status_data['company_number'])
                
            # PID parameters
            if 'pid' in self.latest_status_data:
                if 'kp' in self.latest_status_data['pid']:
                    self.kp_input.setValue(self.latest_status_data['pid']['kp'])
                if 'ki' in self.latest_status_data['pid']:
                    self.ki_input.setValue(self.latest_status_data['pid']['ki'])
                if 'kd' in self.latest_status_data['pid']:
                    self.kd_input.setValue(self.latest_status_data['pid']['kd'])
                if 'deadband' in self.latest_status_data['pid']:
                    self.deadband_input.setValue(self.latest_status_data['pid']['deadband'])
            
            # Velocity limits - Fix for not updating
            if 'velocity' in self.latest_status_data:
                if 'max_descent' in self.latest_status_data['velocity']:
                    self.descent_vel_input.setValue(self.latest_status_data['velocity']['max_descent'])
                if 'max_ascent' in self.latest_status_data['velocity']:
                    self.ascent_vel_input.setValue(self.latest_status_data['velocity']['max_ascent'])
            
            # Target depth
            if 'depth' in self.latest_status_data:
                if 'target' in self.latest_status_data['depth']:
                    self.target_depth_input.setValue(self.latest_status_data['depth']['target'])
                if 'tolerance' in self.latest_status_data['depth']:
                    self.depth_tolerance_input.setValue(self.latest_status_data['depth']['tolerance'])
            
            # Wait time
            if 'routine' in self.latest_status_data and 'wait_time_seconds' in self.latest_status_data['routine']:
                self.wait_time_input.setValue(self.latest_status_data['routine']['wait_time_seconds'])
            
            # Read interval
            if 'queue' in self.latest_status_data and 'read_interval_ms' in self.latest_status_data['queue']:
                self.normal_interval_input.setValue(self.latest_status_data['queue']['read_interval_ms'])
            
            # Check for velocity test mode to update velocity interval
            if 'queue' in self.latest_status_data and 'velocity_interval_ms' in self.latest_status_data['queue']:
                self.velocity_interval_input.setValue(self.latest_status_data['queue']['velocity_interval_ms'])
            
            
            # Check if any values changed and log them
            new_values = {
                'kp': self.kp_input.value(),
                'ki': self.ki_input.value(),
                'kd': self.kd_input.value(),
                'deadband': self.deadband_input.value(),
                'descent_vel': self.descent_vel_input.value(),
                'ascent_vel': self.ascent_vel_input.value(),
                'target_depth': self.target_depth_input.value(),
                'tolerance': self.depth_tolerance_input.value(),
                'wait_time': self.wait_time_input.value(),
                'normal_interval': self.normal_interval_input.value(),
                'velocity_interval': self.velocity_interval_input.value(),
                'company_number': self.company_number_input.value()  # Add this line
            }
            
            # Log changes for debugging
            for key, new_val in new_values.items():
                if new_val != old_values[key]:
                    print(f"Updated {key}: {old_values[key]} -> {new_val}")
                
        except Exception as e:
            print(f"Error updating parameter fields: {e}")
            traceback.print_exc()

    def reset_editing_flag(self):
        """Reset the editing flag to allow auto-updates again"""
        self.editing_fields = False
    
    def flatten_dict(self, d, parent_key='', sep='.'):
        """Flatten a nested dictionary for easier display in a table"""
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self.flatten_dict(v, new_key, sep=sep))
            else:
                items[new_key] = v
        return items
    
    def handle_error(self, error_message):
        """Handle connection errors"""
        print(f"Error: {error_message}")
        
    def send_command(self, command):
        """Send a command to the float"""
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first")
            return
            
        try:
            if command == "s":
                # For start command, need to include the laptop's IP
                hostname = socket.gethostname()
                laptop_ip = socket.gethostbyname(hostname)
                url = f"http://{self.float_ip}/start_signal?ip_address={laptop_ip}"
            elif command == "vs":
                url = f"http://{self.float_ip}/start_velocity"
            elif command == "vst":
                url = f"http://{self.float_ip}/stop_velocity"
            elif command == "st":
                url = f"http://{self.float_ip}/stop_signal"
            elif command == "rs":
                url = f"http://{self.float_ip}/start_routine"
            elif command == "a":
                url = f"http://{self.float_ip}/pump_ascend"
            elif command == "d":
                url = f"http://{self.float_ip}/pump_descend"
            elif command == ".":
                url = f"http://{self.float_ip}/pump_stop"
            elif command == "pid_toggle":
                url = f"http://{self.float_ip}/toggle_pid_control"
            else:
                QMessageBox.warning(self, "Command Error", f"Unknown command: {command}")
                return
                
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"Command {command} sent successfully")
                # Refresh status after command
                QTimer.singleShot(500, self.manual_refresh)
            else:
                QMessageBox.warning(self, "Command Error", f"Server returned status code {response.status_code}")
                
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Failed to send command: {str(e)}")
            traceback.print_exc()
    
    def set_pid_params(self):
        """Set PID parameters"""
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first")
            return
            
        try:
            kp = self.kp_input.value()
            ki = self.ki_input.value()
            kd = self.kd_input.value()
            
            url = f"http://{self.float_ip}/set_pid"
            params = {'kp': kp, 'ki': ki, 'kd': kd}
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                QMessageBox.information(self, "Success", "PID parameters updated successfully")
                # Refresh status
                QTimer.singleShot(500, self.manual_refresh)
            else:
                QMessageBox.warning(self, "Error", f"Failed to update PID parameters: {response.text}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting PID parameters: {str(e)}")
            traceback.print_exc()
    
    def set_pid_deadband(self):
        """Set PID deadband"""
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first")
            return
            
        try:
            deadband = self.deadband_input.value()
            
            url = f"http://{self.float_ip}/set_pid_deadband"
            params = {'value': deadband}
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                QMessageBox.information(self, "Success", "PID deadband updated successfully")
                # Refresh status
                QTimer.singleShot(500, self.manual_refresh)
            else:
                QMessageBox.warning(self, "Error", f"Failed to update PID deadband: {response.text}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting PID deadband: {str(e)}")
            traceback.print_exc()
    
    def set_velocity_limits(self):
        """Set velocity limits"""
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first")
            return
            
        try:
            descent = self.descent_vel_input.value()
            ascent = self.ascent_vel_input.value()
            
            url = f"http://{self.float_ip}/set_velocity"
            params = {'descent': descent, 'ascent': ascent}
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                QMessageBox.information(self, "Success", "Velocity limits updated successfully")
                # Refresh status
                QTimer.singleShot(500, self.manual_refresh)
            else:
                QMessageBox.warning(self, "Error", f"Failed to update velocity limits: {response.text}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting velocity limits: {str(e)}")
            traceback.print_exc()
    
    def set_target_depth(self):
        """Set target depth"""
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first")
            return
            
        try:
            depth = self.target_depth_input.value()
            
            url = f"http://{self.float_ip}/set_target_depth"
            params = {'depth': depth}
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                QMessageBox.information(self, "Success", "Target depth updated successfully")
                # Refresh status
                QTimer.singleShot(500, self.manual_refresh)
            else:
                QMessageBox.warning(self, "Error", f"Failed to update target depth: {response.text}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting target depth: {str(e)}")
            traceback.print_exc()
    
    def set_depth_tolerance(self):
        """Set depth tolerance"""
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first")
            return
            
        try:
            tolerance = self.depth_tolerance_input.value()
            
            url = f"http://{self.float_ip}/set_depth_tolerance"
            params = {'tolerance': tolerance}
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                QMessageBox.information(self, "Success", "Depth tolerance updated successfully")
                # Refresh status
                QTimer.singleShot(500, self.manual_refresh)
            else:
                QMessageBox.warning(self, "Error", f"Failed to update depth tolerance: {response.text}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting depth tolerance: {str(e)}")
            traceback.print_exc()
    
    def set_wait_time(self):
        """Set routine wait time"""
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first")
            return
            
        try:
            seconds = self.wait_time_input.value()
            
            url = f"http://{self.float_ip}/set_wait_time"
            params = {'seconds': seconds}
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                QMessageBox.information(self, "Success", "Wait time updated successfully")
                # Refresh status
                QTimer.singleShot(500, self.manual_refresh)
            else:
                QMessageBox.warning(self, "Error", f"Failed to update wait time: {response.text}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting wait time: {str(e)}")
            traceback.print_exc()
    
    def set_read_intervals(self):
        """Set data read intervals"""
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first")
            return
            
        try:
            normal = self.normal_interval_input.value()
            velocity = self.velocity_interval_input.value()
            
            url = f"http://{self.float_ip}/set_read_intervals"
            params = {'normal': normal, 'velocity': velocity}
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                QMessageBox.information(self, "Success", "Read intervals updated successfully")
                # Refresh status
                QTimer.singleShot(500, self.manual_refresh)
            else:
                QMessageBox.warning(self, "Error", f"Failed to update read intervals: {response.text}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting read intervals: {str(e)}")
            traceback.print_exc()
    
    
    def set_company_number(self):
        """Set company number"""
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first")
            return
            
        try:
            number = self.company_number_input.value()
            
            url = f"http://{self.float_ip}/set_company_number"
            params = {'value': number}
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                QMessageBox.information(self, "Success", "Company number updated successfully")
                # Refresh status
                QTimer.singleShot(500, self.manual_refresh)
            else:
                QMessageBox.warning(self, "Error", f"Failed to update company number: {response.text}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting company number: {str(e)}")
            traceback.print_exc()
            
    def plot_depth_data(self):
        """Plot the depth data collected from the float"""
        if not self.depth_data:
            QMessageBox.warning(self, "Plot Error", "No depth data available to plot")
            return
            
        try:
            # Sort data by time
            sorted_data = sorted(self.depth_data, key=lambda x: x['time'])
            
            # Extract data lists
            times = [item['time'] for item in sorted_data]
            depths = [item['depth'] for item in sorted_data]
            pressures = [item['pressure'] for item in sorted_data]
            velocities = [item['velocity'] for item in sorted_data]
            pid_outputs = [item['pid_output'] for item in sorted_data]
            pid_errors = [item['pid_error'] for item in sorted_data]
            pump_statuses = [item['pump_status'] for item in sorted_data]
            
            # Create interactive subplot figure with 4 subplots
            fig = make_subplots(
                rows=4, 
                cols=1,
                subplot_titles=("Time vs Depth", "Time vs Velocity", "Time vs PID Output", "Time vs PID Error"),
                vertical_spacing=0.1,
                row_heights=[0.35, 0.25, 0.2, 0.2]
            )
            
            # Add traces for each subplot
            # Subplot 1: Time vs. Depth
            fig.add_trace(
                go.Scatter(
                    x=times, 
                    y=depths, 
                    mode='lines+markers',
                    name='Depth',
                    hovertemplate='Time: %{x:.2f}s<br>Depth: %{y:.3f}m<br>Pump: %{text}',
                    text=pump_statuses
                ),
                row=1, col=1
            )
            
            # Add reference lines for target depth if available
            if 'depth' in self.latest_status_data and 'target' in self.latest_status_data['depth']:
                target = self.latest_status_data['depth']['target']
                tolerance = self.latest_status_data['depth']['tolerance'] if 'tolerance' in self.latest_status_data['depth'] else 0.125
                
                # Target line
                fig.add_trace(
                    go.Scatter(
                        x=[min(times), max(times)],
                        y=[target, target],
                        mode='lines',
                        name=f'Target Depth ({target}m)',
                        line=dict(color="green", width=2),
                        hoverinfo='name'
                    ),
                    row=1, col=1
                )
                
                # Min/Max tolerance lines
                fig.add_trace(
                    go.Scatter(
                        x=[min(times), max(times)],
                        y=[target - tolerance, target - tolerance],
                        mode='lines',
                        name=f'Min Target Depth ({target-tolerance:.3f}m)',
                        line=dict(color="red", width=2, dash="dash"),
                        hoverinfo='name'
                    ),
                    row=1, col=1
                )
                
                fig.add_trace(
                    go.Scatter(
                        x=[min(times), max(times)],
                        y=[target + tolerance, target + tolerance],
                        mode='lines',
                        name=f'Max Target Depth ({target+tolerance:.3f}m)',
                        line=dict(color="red", width=2, dash="dash"),
                        hoverinfo='name'
                    ),
                    row=1, col=1
                )
            
            # Subplot 2: Time vs. Velocity
            fig.add_trace(
                go.Scatter(
                    x=times, 
                    y=velocities, 
                    mode='lines',
                    name='Velocity',
                    line=dict(color="orange")
                ),
                row=2, col=1
            )
            
            # Add velocity limit lines if available
            if 'velocity' in self.latest_status_data:
                max_descent = self.latest_status_data['velocity']['max_descent'] if 'max_descent' in self.latest_status_data['velocity'] else 0.18
                max_ascent = self.latest_status_data['velocity']['max_ascent'] if 'max_ascent' in self.latest_status_data['velocity'] else 0.1
                
                fig.add_trace(
                    go.Scatter(
                        x=[min(times), max(times)],
                        y=[max_descent, max_descent],
                        mode='lines',
                        name=f'Max Descent ({max_descent}m/s)',
                        line=dict(color="red", width=1, dash="dash"),
                        hoverinfo='name'
                    ),
                    row=2, col=1
                )
                
                fig.add_trace(
                    go.Scatter(
                        x=[min(times), max(times)],
                        y=[-max_ascent, -max_ascent],
                        mode='lines',
                        name=f'Max Ascent ({max_ascent}m/s)',
                        line=dict(color="red", width=1, dash="dash"),
                        hoverinfo='name'
                    ),
                    row=2, col=1
                )
            
            # Subplot 3: Time vs. PID Output
            fig.add_trace(
                go.Scatter(
                    x=times, 
                    y=pid_outputs, 
                    mode='lines',
                    name='PID Output',
                    line=dict(color="blue")
                ),
                row=3, col=1
            )
            
            # Add deadband lines if available
            if 'pid' in self.latest_status_data and 'deadband' in self.latest_status_data['pid']:
                deadband = self.latest_status_data['pid']['deadband']
                
                fig.add_trace(
                    go.Scatter(
                        x=[min(times), max(times)],
                        y=[deadband, deadband],
                        mode='lines',
                        name=f'Deadband (+{deadband})',
                        line=dict(color="purple", width=1, dash="dash"),
                        hoverinfo='name'
                    ),
                    row=3, col=1
                )
                
                fig.add_trace(
                    go.Scatter(
                        x=[min(times), max(times)],
                        y=[-deadband, -deadband],
                        mode='lines',
                        name=f'Deadband (-{deadband})',
                        line=dict(color="purple", width=1, dash="dash"),
                        hoverinfo='name'
                    ),
                    row=3, col=1
                )
            
            # Subplot 4: Time vs. PID Error
            fig.add_trace(
                go.Scatter(
                    x=times, 
                    y=pid_errors, 
                    mode='lines',
                    name='PID Error',
                    line=dict(color="red")
                ),
                row=4, col=1
            )
            
            # Add a zero line for reference
            fig.add_trace(
                go.Scatter(
                    x=[min(times), max(times)],
                    y=[0, 0],
                    mode='lines',
                    name='Zero Error',
                    line=dict(color="green", width=1, dash="dash"),
                    hoverinfo='name'
                ),
                row=4, col=1
            )
            
            # Update layout
            plot_title = "Float Depth Data"
            if self.current_capture_file:
                plot_title += f" ({self.current_capture_file})"
            
            fig.update_layout(
                title=plot_title,
                height=800,
                width=1000,
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            # Update y-axis labels
            fig.update_yaxes(title_text="Depth (m)", row=1, col=1)
            fig.update_yaxes(title_text="Velocity (m/s)", row=2, col=1)
            fig.update_yaxes(title_text="PID Output", row=3, col=1)
            fig.update_yaxes(title_text="PID Error", row=4, col=1)
            
            # Update x-axis labels, but only show it on the bottom plot
            fig.update_xaxes(title_text="Time (s)", row=4, col=1)
            
            # Show the figure
            fig.show()
            
        except Exception as e:
            QMessageBox.critical(self, "Plot Error", f"Error plotting data: {str(e)}")
            traceback.print_exc()
    
    def save_current_data(self):
        """Save the current depth data to a JSON file"""
        if not self.depth_data:
            QMessageBox.warning(self, "Save Error", "No depth data available to save")
            return
            
        try:
            # Create a timestamp for the filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"float_data_{timestamp}.json"
            filepath = os.path.join(self.data_directory, filename)
            
            # Save the data
            with open(filepath, 'w') as f:
                json.dump(self.depth_data, f, indent=2)
            
            # Also save to coordinates_data.json
            self.save_to_coordinates_json(self.depth_data)
            
            QMessageBox.information(self, "Save Success", f"Data saved to {filepath}")
            
            # Update saved data info
            self.update_saved_data_info()
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Error saving data: {str(e)}")
            traceback.print_exc()
    
    def save_to_coordinates_json(self, data):
        """Save data to the coordinates_data.json file"""
        try:
            coordinates_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                           'json_formats', 'coordinates_data.json')
            
            # Create parent directory if it doesn't exist
            os.makedirs(os.path.dirname(coordinates_path), exist_ok=True)
            
            # Format for coordinates_data.json
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            coordinates_data = {
                "description": f"Float data from {timestamp}",
                "data": data
            }
            
            with open(coordinates_path, 'w') as f:
                json.dump(coordinates_data, f, indent=2)
                
            print(f"Data saved to {coordinates_path}")
        except Exception as e:
            print(f"Warning: Could not save to coordinates_data.json: {e}")
            traceback.print_exc()
    
    def load_and_plot_data(self):
        """Load saved data and plot it"""
        try:
            # Get list of saved data files
            data_files = [f for f in os.listdir(self.data_directory) 
                         if (f.startswith("float_data_") or f.startswith("float_capture_")) and f.endswith(".json")]
            
            if not data_files:
                QMessageBox.warning(self, "Load Error", "No saved data files found")
                return
                
            # Sort by date (newest first)
            data_files.sort(reverse=True)
            
            # Let the user choose the file
            file_path, _ = QFileDialog.getOpenFileName(
                self, 
                "Select Float Data File",
                self.data_directory,
                "JSON Files (*.json)"
            )
            
            if not file_path:
                return  # User canceled
                
            # Load the data
            with open(file_path, 'r') as f:
                loaded_data = json.load(f)
            
            if not loaded_data:
                QMessageBox.warning(self, "Load Error", "The selected file contains no data")
                return
                
            # Set as current data and plot
            self.depth_data = loaded_data
            self.current_capture_file = os.path.basename(file_path)
            self.plot_depth_data()
            
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Error loading data: {str(e)}")
            traceback.print_exc()
    
    def update_saved_data_info(self):
        """Update the saved data information display"""
        try:
            # Get list of saved data files
            data_files = [f for f in os.listdir(self.data_directory) 
                         if (f.startswith("float_data_") or f.startswith("float_capture_")) and f.endswith(".json")]
            
            if not data_files:
                self.saved_data_label.setText("No data saved yet")
                return
                
            # Sort by date (newest first)
            data_files.sort(reverse=True)
            
            # Show info about the most recent files
            info_text = f"Found {len(data_files)} saved data files.\n\nMost recent:\n"
            
            for i, file in enumerate(data_files[:5]):  # Show only 5 most recent
                # Parse timestamp from filename
                if file.startswith("float_data_"):
                    timestamp_str = file.replace("float_data_", "").replace(".json", "")
                else:
                    timestamp_str = file.replace("float_capture_", "").replace(".json", "")
                    
                try:
                    timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    formatted_time = timestamp_str
                
                # Get file size
                filepath = os.path.join(self.data_directory, file)
                size_kb = os.path.getsize(filepath) / 1024
                
                # Count data points
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        points = len(data)
                except:
                    points = "unknown"
                
                info_text += f"{i+1}. {formatted_time} ({size_kb:.1f} KB, {points} points)\n"
            
            self.saved_data_label.setText(info_text)
            
        except Exception as e:
            self.saved_data_label.setText(f"Error retrieving saved data info: {str(e)}")
            traceback.print_exc()
            
    def closeEvent(self, event):
        """Clean up resources when widget is closed"""
        # Stop the capture if it's running
        if self.capturing_data:
            self.stop_capture()
            
        # Stop the worker
        if self.worker:
            self.worker.stop()
            
        # Stop the timers
        self.auto_update_timer.stop()
        self.local_time_timer.stop()
        
        super().closeEvent(event)