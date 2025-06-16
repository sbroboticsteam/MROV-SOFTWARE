import requests
import json
import traceback
import os
import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QLineEdit, QTableWidget, QTableWidgetItem, QFormLayout,
                            QGroupBox, QTabWidget, QDoubleSpinBox, QSpinBox, QMessageBox,
                            QHeaderView, QCheckBox, QApplication) # Added QApplication for clipboard
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QPointF
import socket
import pyqtgraph as pg
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading # For running HTTPServer in a non-blocking way via QThread

# Configure pyqtgraph
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')
pg.setConfigOption('antialias', True)


class FloatDataHandler(BaseHTTPRequestHandler):
    # Class variable to hold a reference to the data_received_signal
    data_received_signal = None
    gui_capture_start_time_ref = None # To calculate GUI time relative to capture start

    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data_list = json.loads(post_data.decode('utf-8')).get("data", [])

            if FloatDataHandler.data_received_signal and data_list:
                gui_received_time = datetime.datetime.now()
                # Emit the raw list and the receipt time
                FloatDataHandler.data_received_signal.emit(data_list, gui_received_time)

            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Data received by GUI")
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Error processing data: {str(e)}".encode('utf-8'))
            print(f"Error in FloatDataHandler: {e}")
            traceback.print_exc()

    def log_message(self, format, *args):
        # Suppress HTTP server log messages to console if not needed
        # print(f"HTTP Server: {format % args}")
        return


class FloatDataReceiverThread(QThread):
    data_received = pyqtSignal(list, datetime.datetime) # list of measurements, gui_received_timestamp
    server_error = pyqtSignal(str)

    def __init__(self, host='0.0.0.0', port=8000):
        super().__init__()
        self.host = host
        self.port = port
        self.httpd = None
        self.running = False
        FloatDataHandler.data_received_signal = self.data_received


    def run(self):
        self.running = True
        try:
            self.httpd = HTTPServer((self.host, self.port), FloatDataHandler)
            print(f"GUI HTTP Server started on {self.host}:{self.port}, listening for float data...")
            while self.running:
                self.httpd.handle_request() # Process one request at a time
            if self.httpd:
                self.httpd.server_close()
            print("GUI HTTP Server stopped.")
        except socket.error as e:
            if e.errno == 98: # Address already in use
                 self.server_error.emit(f"Error: Port {self.port} is already in use. Cannot start data receiver.")
            else:
                self.server_error.emit(f"GUI HTTP Server error: {str(e)}")
            traceback.print_exc()
        except Exception as e:
            self.server_error.emit(f"GUI HTTP Server unexpected error: {str(e)}")
            traceback.print_exc()
        finally:
            if self.httpd:
                self.httpd.server_close() # Ensure it's closed

    def stop_server(self):
        self.running = False
        if self.httpd:
            # To unblock httpd.handle_request(), send a dummy request to it
            try:
                # Create a temporary client to connect and send a minimal request
                # This helps httpd.handle_request() to exit if it's blocking
                with socket.create_connection((self.host if self.host != '0.0.0.0' else '127.0.0.1', self.port), timeout=0.1) as sock:
                    sock.sendall(b"GET /shutdown HTTP/1.1\r\nHost: localhost\r\n\r\n")
            except Exception:
                pass # Ignore errors during shutdown signaling
            self.httpd.server_close() # Close the server socket
        self.wait(2000) # Wait for the thread to finish


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
                response = requests.get(url, timeout=3) # Shorter timeout for status
                if response.status_code == 200:
                    self.status_received.emit(response.json())
                else:
                    self.error_occurred.emit(f"Status Error: Code {response.status_code}")
            except requests.exceptions.RequestException as e: # More specific exception
                self.error_occurred.emit(f"Status Connection error: {str(e)}")
            
            self.msleep(2000) # Poll status every 2 seconds

    def stop(self):
        self.running = False
        self.wait()


class FloatController(QWidget):
    """Widget for controlling and monitoring the MATE ROV Float"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status_worker = None
        self.data_receiver_thread = None
        self.float_ip = ""
        self.data_directory = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'float_data')
        if not os.path.exists(self.data_directory):
            os.makedirs(self.data_directory)

        self.capturing_data = False
        self.capture_start_time_gui = None # GUI's perspective of when capture started
        self.current_capture_file = None

        self.editing_fields = False
        self.auto_update_timer = QTimer()
        self.auto_update_timer.timeout.connect(self.update_parameter_fields)
        self.auto_update_timer.start(10000)

        self.latest_status_data = {}
        self.logged_data_points = [] # For saving captured data (now richer)

        # Data for live plots
        self.plot_float_time = [] # Float's timeSinceStart
        self.plot_depth_data = []
        self.plot_velocity_data = []
        
        self.plot_arrival_float_time = [] # Float time for arrival plot
        self.plot_arrival_gui_time_numeric = [] # GUI time (numeric) for arrival plot

        self.max_plot_points = 300

        self.hover_text_item = None # For pyqtgraph hover text

        self.setupUI()
        self.start_data_receiver() # Start it once

    def start_data_receiver(self):
        if self.data_receiver_thread is None or not self.data_receiver_thread.isRunning():
            self.data_receiver_thread = FloatDataReceiverThread()
            FloatDataHandler.gui_capture_start_time_ref = lambda: self.capture_start_time_gui
            self.data_receiver_thread.data_received.connect(self.handle_float_data_packet)
            self.data_receiver_thread.server_error.connect(self.handle_data_server_error)
            self.data_receiver_thread.start()

    def handle_data_server_error(self, error_msg):
        QMessageBox.critical(self, "Data Receiver Error", error_msg)
        print(f"Data Receiver Error: {error_msg}")
        # Potentially try to restart or disable data capture if server fails critically

    def setupUI(self):
        main_layout = QVBoxLayout()

        # ... (IP input and Connect button layout - unchanged) ...
        ip_layout = QHBoxLayout()
        ip_label = QLabel("Float IP:")
        self.ip_input = QLineEdit("192.168.1.226")
        connect_btn = QPushButton("Connect to Float Status")
        connect_btn.clicked.connect(self.connect_to_float_status)
        ip_layout.addWidget(ip_label)
        ip_layout.addWidget(self.ip_input)
        ip_layout.addWidget(connect_btn)
        main_layout.addLayout(ip_layout)

        tabs = QTabWidget()

        # Status tab (largely unchanged, populated by FloatStatusWorker)
        status_tab = QWidget()
        status_layout_main = QVBoxLayout()
        self.status_table = QTableWidget(0, 2)
        self.status_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.status_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.status_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.status_table.verticalHeader().setVisible(False)
        status_layout_main.addWidget(self.status_table)
        refresh_btn = QPushButton("Refresh Status Manually")
        refresh_btn.clicked.connect(self.manual_refresh_status)
        status_layout_main.addWidget(refresh_btn)
        status_tab.setLayout(status_layout_main)
        tabs.addTab(status_tab, "Status")

        # Controls tab (unchanged)
        control_tab = QWidget()
        control_layout = QVBoxLayout()
        basic_group = QGroupBox("Basic Controls")
        basic_layout_form = QFormLayout() # Changed to QFormLayout for better alignment
        #basic_layout = QHBoxLayout()
        start_btn = QPushButton("Start Float (/start_signal)")
        start_btn.clicked.connect(lambda: self.send_command_to_float("s"))
        stop_btn = QPushButton("Stop Float (/stop_signal)")
        stop_btn.clicked.connect(lambda: self.send_command_to_float("st"))
        start_routine_btn = QPushButton("Start Routine (/start_routine)")
        start_routine_btn.clicked.connect(lambda: self.send_command_to_float("rs"))
        recalibrate_depth_btn = QPushButton("Recalibrate Depth Zero (/recalibrate_depth)") # New Button
        recalibrate_depth_btn.clicked.connect(self.recalibrate_depth_on_float) # New Method
        basic_layout_form.addRow(start_btn, stop_btn)
        basic_layout_form.addRow(start_routine_btn, recalibrate_depth_btn) # Added button here
        basic_group.setLayout(basic_layout_form)
        
        control_layout.addWidget(basic_group)

        pump_group = QGroupBox("Pump Controls (Manual - if routine is not active)")
        pump_layout = QHBoxLayout()
        ascend_btn = QPushButton("Ascend")
        ascend_btn.clicked.connect(lambda: self.send_command_to_float("a"))
        descend_btn = QPushButton("Descend")
        descend_btn.clicked.connect(lambda: self.send_command_to_float("d"))
        pump_stop_btn = QPushButton("Stop Pump")
        pump_stop_btn.clicked.connect(lambda: self.send_command_to_float("."))
        pump_layout.addWidget(ascend_btn)
        pump_layout.addWidget(descend_btn)
        pump_layout.addWidget(pump_stop_btn)
        pump_group.setLayout(pump_layout)
        control_layout.addWidget(pump_group)

        capture_group = QGroupBox("Data Capture Log (from /depth endpoint)")
        capture_layout = QVBoxLayout()
        capture_btn_layout = QHBoxLayout()
        self.start_capture_btn = QPushButton("Start New Capture Log")
        self.start_capture_btn.clicked.connect(self.start_new_capture)
        self.stop_capture_btn = QPushButton("Stop Capture Log & Save")
        self.stop_capture_btn.clicked.connect(self.stop_capture)
        self.stop_capture_btn.setEnabled(False)
        capture_btn_layout.addWidget(self.start_capture_btn)
        capture_btn_layout.addWidget(self.stop_capture_btn)
        self.capture_status_label = QLabel("Data capture log not active. Waiting for data from float on port 8000.")
        capture_layout.addLayout(capture_btn_layout)
        capture_layout.addWidget(self.capture_status_label)
        capture_group.setLayout(capture_layout)
        control_layout.addWidget(capture_group)
        control_tab.setLayout(control_layout)
        tabs.addTab(control_tab, "Controls")

        # Parameters tab (unchanged)
        param_tab = QWidget()
        param_layout = QVBoxLayout()
        auto_update_layout = QHBoxLayout()
        self.auto_update_checkbox = QCheckBox("Auto-update parameter fields from float status")
        self.auto_update_checkbox.setChecked(True)
        self.auto_update_checkbox.stateChanged.connect(self.toggle_auto_update)
        auto_update_layout.addWidget(self.auto_update_checkbox)
        auto_update_layout.addStretch()
        manual_update_param_btn = QPushButton("Refresh Parameter Fields Now (from last status)")
        manual_update_param_btn.clicked.connect(self.update_parameter_fields)
        auto_update_layout.addWidget(manual_update_param_btn)
        param_layout.addLayout(auto_update_layout)

        depth_group = QGroupBox("Target Depth")
        depth_form = QFormLayout()
        self.target_depth_input = QDoubleSpinBox()
        self.target_depth_input.setRange(0, 10); self.target_depth_input.setDecimals(3); self.target_depth_input.setSingleStep(0.1)
        self.target_depth_input.valueChanged.connect(self.parameter_editing_started)
        depth_form.addRow("Target Depth (m):", self.target_depth_input)
        set_depth_btn = QPushButton("Set Target Depth"); set_depth_btn.clicked.connect(self.set_target_depth)
        depth_group.setLayout(depth_form); param_layout.addWidget(depth_group); param_layout.addWidget(set_depth_btn)

        wait_group = QGroupBox("Routine Wait Time at Target")
        wait_form = QFormLayout()
        self.wait_time_input = QSpinBox(); self.wait_time_input.setRange(1, 600); self.wait_time_input.setSingleStep(1)
        self.wait_time_input.valueChanged.connect(self.parameter_editing_started)
        wait_form.addRow("Wait Time (seconds):", self.wait_time_input)
        set_wait_btn = QPushButton("Set Wait Time"); set_wait_btn.clicked.connect(self.set_wait_time)
        wait_group.setLayout(wait_form); param_layout.addWidget(wait_group); param_layout.addWidget(set_wait_btn)
        
        company_group = QGroupBox("Company Settings")
        company_form = QFormLayout()
        self.company_number_input = QSpinBox(); self.company_number_input.setRange(1, 99999); self.company_number_input.setSingleStep(1)
        self.company_number_input.valueChanged.connect(self.parameter_editing_started)
        company_form.addRow("Company Number:", self.company_number_input)
        set_company_btn = QPushButton("Set Company Number"); set_company_btn.clicked.connect(self.set_company_number)
        company_group.setLayout(company_form); param_layout.addWidget(company_group); param_layout.addWidget(set_company_btn)
        param_layout.addStretch(); param_tab.setLayout(param_layout); tabs.addTab(param_tab, "Parameters")

        # Dashboard tab
        dashboard_tab = QWidget()
        dashboard_main_layout = QVBoxLayout() # Main layout for dashboard
        
        # Split dashboard into two columns: Info Panels | Plots
        dashboard_splitter = QHBoxLayout()

        # Left Column: Info Panels
        info_panels_layout = QVBoxLayout()

        # ... (Company Info, Time Info, Depth/Pressure, System Status groups - largely unchanged, updated by /status poll) ...
        company_info_group = QGroupBox("Company Information")
        company_layout = QFormLayout()
        company_name_label = QLabel("SBRT"); company_name_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.company_number_label = QLabel("--"); self.company_number_label.setStyleSheet("font-size: 16px;")
        company_layout.addRow("Company Name:", company_name_label); company_layout.addRow("Company Number:", self.company_number_label)
        company_info_group.setLayout(company_layout); info_panels_layout.addWidget(company_info_group)

        time_group = QGroupBox("Time Information (from /status)")
        time_layout = QFormLayout()
        self.float_time_label = QLabel("--"); self.float_time_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.float_uptime_label = QLabel("--"); self.local_time_label = QLabel("--")
        time_layout.addRow("Float Uptime (s):", self.float_time_label); time_layout.addRow("Float Uptime (H:M:S):", self.float_uptime_label)
        time_layout.addRow("Local Time:", self.local_time_label)
        time_group.setLayout(time_layout); info_panels_layout.addWidget(time_group)

        depth_pressure_group = QGroupBox("Real-time Vitals (from /status)")
        depth_layout_form = QFormLayout()
        self.current_depth_label = QLabel("--"); self.current_depth_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.current_pressure_label = QLabel("--"); self.current_pressure_label.setStyleSheet("font-size: 18px;")
        self.target_depth_dashboard_label = QLabel("--") # Renamed to avoid clash
        self.depth_error_label = QLabel("--")
        depth_layout_form.addRow("Current Depth:", self.current_depth_label); depth_layout_form.addRow("Current Pressure:", self.current_pressure_label)
        depth_layout_form.addRow("Target Depth:", self.target_depth_dashboard_label); depth_layout_form.addRow("Depth Error:", self.depth_error_label)
        depth_pressure_group.setLayout(depth_layout_form); info_panels_layout.addWidget(depth_pressure_group)
        
        system_status_group = QGroupBox("System Status (from /status)")
        status_layout_form = QFormLayout()
        self.pump_status_label = QLabel("--"); self.routine_status_label = QLabel("--"); self.wifi_status_label = QLabel("--")
        status_layout_form.addRow("Pump:", self.pump_status_label); status_layout_form.addRow("Routine:", self.routine_status_label)
        status_layout_form.addRow("WiFi Signal:", self.wifi_status_label)
        system_status_group.setLayout(status_layout_form); info_panels_layout.addWidget(system_status_group)
        
        # LED Legend (unchanged)
        led_legend_group = QGroupBox("Float LED Status Legend")
        # ... (LED legend table setup as before) ...
        led_legend_layout = QVBoxLayout()
        self.led_legend_table = QTableWidget()
        self.led_legend_table.setColumnCount(2); self.led_legend_table.setHorizontalHeaderLabels(["Condition", "LED Color/Pattern"])
        self.led_legend_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch); self.led_legend_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.led_legend_table.verticalHeader().setVisible(False)
        legend_data = [("Not Started, WiFi Not Connected", "Solid RED"),("Not Started, WiFi Connected", "Blinking RED/GREEN"),
                       ("Started, WiFi Connected, Routine Idle", "Solid GREEN"),("Started, WiFi Not Connected, Routine Idle", "Solid RED"),
                       ("Routine Active: Queue <= 20 (Base)", "BLUE"),("Routine Active: Queue > 20 (Base)", "YELLOW"),
                       ("Routine Active: Overlay Blink - WiFi Not Connected", "Alt Base / RED"),("Routine Active: Overlay Blink - WiFi Connected", "Alt Base / GREEN"),
                       ("Routine Complete", "Solid WHITE (5s)")]
        self.led_legend_table.setRowCount(len(legend_data))
        for row, (condition, pattern) in enumerate(legend_data):
            self.led_legend_table.setItem(row, 0, QTableWidgetItem(condition)); self.led_legend_table.setItem(row, 1, QTableWidgetItem(pattern))
        self.led_legend_table.resizeRowsToContents()
        table_height = self.led_legend_table.horizontalHeader().height() + 2
        for i in range(self.led_legend_table.rowCount()): table_height += self.led_legend_table.rowHeight(i)
        self.led_legend_table.setMinimumHeight(table_height if table_height < 200 else 200)
        self.led_legend_table.setMaximumHeight(250)
        led_legend_layout.addWidget(self.led_legend_table); led_legend_group.setLayout(led_legend_layout)
        info_panels_layout.addWidget(led_legend_group)
        info_panels_layout.addStretch()
        dashboard_splitter.addLayout(info_panels_layout, 1) # Assign stretch factor 1

        # Right Column: Plots
        plots_area_layout = QVBoxLayout()
        
        self.hover_text_item = pg.TextItem(anchor=(0,1), color=(0,0,0), fill=(255,255,255,180)) # For hover text
        self.hover_text_item.setZValue(100) # Ensure it's on top
        self.hover_text_item.hide()

        self.depth_plot_widget = pg.PlotWidget(title="Depth vs. Float Time (from /depth)")
        self.depth_plot_widget.setLabel('left', "Depth (m)"); self.depth_plot_widget.setLabel('bottom', "Float Time Since Start (s)")
        self.depth_plot_widget.showGrid(x=True, y=True)
        self.depth_curve = self.depth_plot_widget.plot(pen='b', name="Depth")
        self.depth_plot_widget.addItem(self.hover_text_item) # Add hover item to one plot, will be positioned globally
        self.depth_plot_widget.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.depth_plot_widget, [self.depth_curve], ["Depth"]))
        plots_area_layout.addWidget(self.depth_plot_widget)

        self.velocity_plot_widget = pg.PlotWidget(title="Velocity vs. Float Time (from /depth)")
        self.velocity_plot_widget.setLabel('left', "Velocity (m/s)"); self.velocity_plot_widget.setLabel('bottom', "Float Time Since Start (s)")
        self.velocity_plot_widget.showGrid(x=True, y=True)
        self.velocity_curve = self.velocity_plot_widget.plot(pen='r', name="Velocity")
        self.velocity_plot_widget.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.velocity_plot_widget, [self.velocity_curve], ["Velocity"]))
        plots_area_layout.addWidget(self.velocity_plot_widget)

        self.arrival_plot_widget = pg.PlotWidget(title="Data Packet Arrival Times")
        self.arrival_plot_widget.setLabel('left', "GUI Time Since Capture Start (s)")
        self.arrival_plot_widget.setLabel('bottom', "Float Time Since Start (s)")
        self.arrival_plot_widget.showGrid(x=True, y=True)
        self.arrival_curve = self.arrival_plot_widget.plot(pen=None, symbol='o', symbolPen='g', symbolBrush='g', name="Arrivals") # Scatter plot
        self.arrival_plot_widget.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.arrival_plot_widget, [self.arrival_curve], ["GUI Time"]))
        plots_area_layout.addWidget(self.arrival_plot_widget)
        
        dashboard_splitter.addLayout(plots_area_layout, 2) # Assign stretch factor 2 (plots take more space)
        dashboard_main_layout.addLayout(dashboard_splitter)

        self.local_time_timer = QTimer()
        self.local_time_timer.timeout.connect(self.update_local_time)
        self.local_time_timer.start(1000)

        dashboard_tab.setLayout(dashboard_main_layout)
        tabs.addTab(dashboard_tab, "Dashboard")

        main_layout.addWidget(tabs)
        self.setLayout(main_layout)

    def on_mouse_moved(self, pos, plot_widget, curves, curve_names):
        vb = plot_widget.plotItem.vb
        mouse_point = vb.mapSceneToView(pos)
        x_mouse, y_mouse = mouse_point.x(), mouse_point.y()
        
        found_point = False
        text = ""

        for i, curve in enumerate(curves):
            if curve.yData is None or len(curve.yData) == 0:
                continue

            # Find the closest point on this curve
            # This is a simplified proximity check; pyqtgraph has internal ways too
            # For line plots, checking distance to line segments is complex.
            # For scatter or line with symbols, checking distance to points is easier.
            # Here, we'll find the point with the closest x-value.
            
            x_data = curve.xData
            y_data = curve.yData

            if x_data is None or y_data is None or len(x_data) == 0:
                continue

            # Find index of closest x_data point
            # This is not perfect for hover, sigPointsHovered is better if available directly on curve
            # For now, let's find the closest x and check if mouse y is near curve y
            
            # A simpler way: check if mouse is within the plot area
            if plot_widget.plotItem.sceneBoundingRect().contains(pos):
                min_dist_sq = float('inf')
                closest_pt_idx = -1

                for idx in range(len(x_data)):
                    pt_view = QPointF(x_data[idx], y_data[idx])
                    pt_scene = vb.mapViewToScene(pt_view)
                    dist_sq = (pos.x() - pt_scene.x())**2 + (pos.y() - pt_scene.y())**2
                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq
                        closest_pt_idx = idx
                
                # Threshold for hover (e.g., 10 pixels squared)
                if closest_pt_idx != -1 and min_dist_sq < 100: # 10px radius
                    x_val = x_data[closest_pt_idx]
                    y_val = y_data[closest_pt_idx]
                    text += f"{curve_names[i]}:\n  Time: {x_val:.2f}s\n  Value: {y_val:.3f}\n"
                    found_point = True
        
        if found_point:
            self.hover_text_item.setText(text.strip())
            self.hover_text_item.setPos(mouse_point.x(), mouse_point.y()) # Position near mouse
            # Ensure hover_text_item is associated with the current plot_widget's viewbox if it's shared
            if self.hover_text_item.getViewBox() is None or self.hover_text_item.getViewBox() != vb:
                 if self.hover_text_item.getViewBox(): # Remove from old viewbox if any
                     self.hover_text_item.getViewBox().removeItem(self.hover_text_item)
                 vb.addItem(self.hover_text_item) # Add to current viewbox
            self.hover_text_item.show()
        else:
            self.hover_text_item.hide()


    def parameter_editing_started(self):
        self.editing_fields = True
        if self.auto_update_checkbox.isChecked():
            self.auto_update_timer.start(10000)

    def toggle_auto_update(self, state):
        if state == Qt.Checked:
            self.auto_update_timer.start(10000)
            self.update_parameter_fields()
        else:
            self.auto_update_timer.stop()

    def start_new_capture(self):
        self.logged_data_points = []
        self.plot_float_time.clear(); self.plot_depth_data.clear(); self.plot_velocity_data.clear()
        self.plot_arrival_float_time.clear(); self.plot_arrival_gui_time_numeric.clear()
        
        self.depth_curve.clear(); self.velocity_curve.clear(); self.arrival_curve.clear()

        self.capturing_data = True
        self.capture_start_time_gui = datetime.datetime.now() # GUI's capture start time
        FloatDataHandler.gui_capture_start_time_ref = lambda: self.capture_start_time_gui # Update ref

        timestamp = self.capture_start_time_gui.strftime("%Y%m%d_%H%M%S")
        self.current_capture_file = f"float_capture_{timestamp}.json"
        
        self.start_capture_btn.setEnabled(False)
        self.stop_capture_btn.setEnabled(True)
        self.capture_status_label.setText(f"Logging data to {self.current_capture_file} (from /depth)")
        QMessageBox.information(self, "Data Capture Log Started",
                               f"Started new data log.\nData from float's /depth endpoint will be saved to {self.current_capture_file} upon stopping.")

    def stop_capture(self):
        if not self.capturing_data:
            return
        self.capturing_data = False
        if self.logged_data_points and self.current_capture_file:
            filepath = os.path.join(self.data_directory, self.current_capture_file)
            try:
                with open(filepath, 'w') as f:
                    json.dump(self.logged_data_points, f, indent=2)
                # self.save_to_coordinates_json(self.logged_data_points) # If you still need this specific format
                
                self.start_capture_btn.setEnabled(True)
                self.stop_capture_btn.setEnabled(False)
                self.capture_status_label.setText(f"Capture log stopped. Saved {len(self.logged_data_points)} points.")
                QMessageBox.information(self, "Data Capture Log Completed",
                                      f"Saved {len(self.logged_data_points)} data points to {self.current_capture_file}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Error saving capture log: {str(e)}")
                traceback.print_exc()
        else:
            self.start_capture_btn.setEnabled(True)
            self.stop_capture_btn.setEnabled(False)
            self.capture_status_label.setText("Capture log stopped. No data to save.")
        self.capture_start_time_gui = None # Reset GUI capture start time
        FloatDataHandler.gui_capture_start_time_ref = lambda: self.capture_start_time_gui # Update ref

    def connect_to_float_status(self): # Renamed to be specific
        self.float_ip = self.ip_input.text().strip()
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please enter a valid IP address for the float.")
            return
        if self.status_worker and self.status_worker.isRunning():
            self.status_worker.stop()
        self.status_worker = FloatStatusWorker(self.float_ip)
        self.status_worker.status_received.connect(self.update_dashboard_from_status) # Changed target
        self.status_worker.error_occurred.connect(self.handle_status_error)
        self.status_worker.start()
        self.manual_refresh_status()
        QMessageBox.information(self, "Status Connection", f"Attempting to connect to float at {self.float_ip} for status updates.")


    def manual_refresh_status(self):
        if not self.float_ip:
            QMessageBox.warning(self, "Connection Error", "Please connect to a float first (for status).")
            return
        try:
            url = f"http://{self.float_ip}/status"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                self.update_dashboard_from_status(response.json())
            else:
                self.handle_status_error(f"Error: Server returned status code {response.status_code}")
        except Exception as e:
            self.handle_status_error(f"Connection error: {str(e)}")

    def handle_float_data_packet(self, measurements_list, gui_received_timestamp):
        if not self.capturing_data or not self.capture_start_time_gui:
            return # Only process if capturing

        gui_time_numeric = (gui_received_timestamp - self.capture_start_time_gui).total_seconds()

        for m_data in measurements_list:
            try:
                float_time = m_data.get('time') # This is float's timeSinceStart
                depth = m_data.get('depth')
                velocity = m_data.get('velocity')
                pressure = m_data.get('pressure')
                pump_status = m_data.get('pump_status', 'unknown')

                if float_time is None or depth is None or velocity is None:
                    print(f"Skipping incomplete data point: {m_data}")
                    continue

                # Log the comprehensive data point
                logged_point = {
                    'float_time_since_start': float_time,
                    'depth': depth,
                    'velocity': velocity,
                    'pressure': pressure,
                    'pump_status': pump_status,
                    'gui_received_timestamp_abs': gui_received_timestamp.isoformat(),
                    'gui_time_since_capture_start': gui_time_numeric
                }
                self.logged_data_points.append(logged_point)

                # Update plot data lists
                self.plot_float_time.append(float_time)
                self.plot_depth_data.append(depth)
                self.plot_velocity_data.append(velocity)
                
                self.plot_arrival_float_time.append(float_time)
                self.plot_arrival_gui_time_numeric.append(gui_time_numeric)

                # Keep plot data lists to max_plot_points
                while len(self.plot_float_time) > self.max_plot_points:
                    self.plot_float_time.pop(0)
                    self.plot_depth_data.pop(0)
                    self.plot_velocity_data.pop(0)
                while len(self.plot_arrival_float_time) > self.max_plot_points:
                    self.plot_arrival_float_time.pop(0)
                    self.plot_arrival_gui_time_numeric.pop(0)
                
                # Update plots
                self.depth_curve.setData(self.plot_float_time, self.plot_depth_data)
                self.velocity_curve.setData(self.plot_float_time, self.plot_velocity_data)
                self.arrival_curve.setData(self.plot_arrival_float_time, self.plot_arrival_gui_time_numeric)

                if len(self.logged_data_points) % 20 == 0 and self.current_capture_file: # Periodic save
                    try:
                        filepath = os.path.join(self.data_directory, self.current_capture_file)
                        with open(filepath, 'w') as f: json.dump(self.logged_data_points, f, indent=2)
                        self.capture_status_label.setText(f"Logging: {len(self.logged_data_points)} points recorded (from /depth)")
                    except Exception as e: print(f"Error auto-saving capture log: {e}")

            except Exception as e:
                print(f"Error processing individual measurement for logging/plotting: {e}, Data: {m_data}")
                traceback.print_exc()
        
        # Update capture status label with the latest count
        self.capture_status_label.setText(f"Logging: {len(self.logged_data_points)} points recorded (from /depth)")


    def update_local_time(self):
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.local_time_label.setText(current_time)

    def update_dashboard_from_status(self, status_data): # Renamed
        self.latest_status_data = status_data # Keep for parameter tab and status table
        
        # Update Status Table
        self.status_table.setRowCount(0)
        flat_data = self.flatten_dict(status_data)
        for i, (key, value) in enumerate(flat_data.items()):
            self.status_table.insertRow(i)
            self.status_table.setItem(i, 0, QTableWidgetItem(key))
            self.status_table.setItem(i, 1, QTableWidgetItem(str(value)))

        # Update Dashboard Info Panels
        if not status_data: return
        self.company_number_label.setText(str(status_data.get('company_number', '--')))
        uptime_seconds = status_data.get('uptime_seconds')
        if uptime_seconds is not None:
            self.float_time_label.setText(f"{uptime_seconds:.1f} s")
            h, rem = divmod(uptime_seconds, 3600); m, s = divmod(rem, 60)
            self.float_uptime_label.setText(f"{int(h)}:{int(m):02d}:{int(s):02d}")
        else: self.float_time_label.setText("--"); self.float_uptime_label.setText("--")

        depth_info = status_data.get('depth', {})
        self.current_depth_label.setText(f"{depth_info.get('current', 0):.3f} m")
        self.current_pressure_label.setText(f"{depth_info.get('pressure', 0):.2f} mbar")
        self.target_depth_dashboard_label.setText(f"{depth_info.get('target', 0):.3f} m") # Use renamed label

        current_depth_val = depth_info.get('current'); target_depth_val = depth_info.get('target')
        if current_depth_val is not None and target_depth_val is not None:
            error = current_depth_val - target_depth_val; self.depth_error_label.setText(f"{error:.3f} m")
            style = "font-weight: bold; color: "; style += "green;" if abs(error) < 0.05 else "orange;" if abs(error) < 0.1 else "red;"
            self.depth_error_label.setStyleSheet(style)
        else: self.depth_error_label.setText("--"); self.depth_error_label.setStyleSheet("")

        pump_state = status_data.get('pump', {}).get('state', 'unknown')
        self.pump_status_label.setText(pump_state.capitalize())
        if pump_state == "off": self.pump_status_label.setStyleSheet("color: gray;")
        elif pump_state == "ascending": self.pump_status_label.setStyleSheet("color: blue; font-weight: bold;")
        elif pump_state == "descending": self.pump_status_label.setStyleSheet("color: red; font-weight: bold;")
        else: self.pump_status_label.setStyleSheet("")

        routine_data = status_data.get('routine', {})
        if routine_data.get('active', False):
            state = routine_data.get('state', 'Unknown'); wait_rem = routine_data.get('collection_timeout_remaining_seconds')
            text = f"Active: {state.replace('_', ' ').capitalize()}"
            if state == "collecting_data_at_target" and wait_rem is not None: text += f" ({wait_rem}s left)"
            self.routine_status_label.setText(text); self.routine_status_label.setStyleSheet("color: green; font-weight: bold;")
        else: self.routine_status_label.setText("Inactive"); self.routine_status_label.setStyleSheet("color: gray;")

        wifi_data = status_data.get('wifi', {}); rssi = wifi_data.get('rssi'); good_sig = wifi_data.get('good_signal')
        if rssi is not None and good_sig is not None:
            self.wifi_status_label.setText(f"{rssi} dBm ({'Good' if good_sig else 'Poor'})")
            self.wifi_status_label.setStyleSheet("font-weight: bold; color: green;" if good_sig else "font-weight: bold; color: red;")
        else: self.wifi_status_label.setText("--"); self.wifi_status_label.setStyleSheet("")

        if self.auto_update_checkbox.isChecked() and not self.editing_fields:
            self.update_parameter_fields() # Update param tab from this status
        if self.editing_fields:
            QTimer.singleShot(10000, self.reset_editing_flag)


    def update_parameter_fields(self): # Uses self.latest_status_data
        if not self.latest_status_data: return
        try:
            if 'company_number' in self.latest_status_data: self.company_number_input.setValue(self.latest_status_data['company_number'])
            if 'depth' in self.latest_status_data and 'target' in self.latest_status_data['depth']: self.target_depth_input.setValue(self.latest_status_data['depth']['target'])
            if 'routine' in self.latest_status_data and 'wait_time_seconds_config' in self.latest_status_data['routine']: self.wait_time_input.setValue(self.latest_status_data['routine']['wait_time_seconds_config'])
        except Exception as e: print(f"Error updating parameter fields: {e}"); traceback.print_exc()

    def reset_editing_flag(self): self.editing_fields = False

    def flatten_dict(self, d, parent_key='', sep='.'):
        items = {}; 
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict): items.update(self.flatten_dict(v, new_key, sep=sep))
            else: items[new_key] = v
        return items

    def handle_status_error(self, error_message): # Renamed
        print(f"Status Error: {error_message}")
        # Potentially update a status bar in UI

    def send_command_to_float(self, command_char_code): # Renamed
        if not self.float_ip: QMessageBox.warning(self, "Command Error", "Float IP not set. Connect to status first."); return
        try:
            url_map = {"s": "/start_signal", "st": "/stop_signal", "rs": "/start_routine",
                       "a": "/pump_ascend", "d": "/pump_descend", ".": "/pump_stop"}
            endpoint = url_map.get(command_char_code)
            if not endpoint: QMessageBox.warning(self, "Command Error", f"Unknown command code: {command_char_code}"); return

            url = f"http://{self.float_ip}{endpoint}"; params = {}
            if command_char_code == "s": # Start signal requires GUI's IP
                try: laptop_ip = socket.gethostbyname(socket.gethostname()) # This might fail if hostname not resolvable
                except socket.gaierror: # Fallback or error
                    active_ip = self.get_active_ip_address()
                    if not active_ip or active_ip == '127.0.0.1':
                        QMessageBox.critical(self, "Network Error", "Could not determine active IP address for the GUI machine. Float cannot send data back.")
                        return
                    laptop_ip = active_ip
                params['ip_address'] = laptop_ip
            
            response = requests.get(url, params=params if params else None, timeout=5)
            if response.status_code == 200:
                print(f"Command '{command_char_code}' sent. Response: {response.text}")
                QMessageBox.information(self, "Command Sent", f"Command '{endpoint}' sent.\nResponse: {response.text}")
                QTimer.singleShot(500, self.manual_refresh_status) # Refresh status after command
            else: QMessageBox.warning(self, "Command Error", f"Server: {response.status_code}: {response.text}")
        except Exception as e: QMessageBox.critical(self, "Connection Error", f"Cmd '{command_char_code}': {str(e)}"); traceback.print_exc()

    def recalibrate_depth_on_float(self):
        if not self.float_ip:
            QMessageBox.warning(self, "Command Error", "Float IP not set. Connect to status first.")
            return
        try:
            url = f"http://{self.float_ip}/recalibrate_depth"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"Command '/recalibrate_depth' sent. Response: {response.text}")
                QMessageBox.information(self, "Command Sent", f"Command '/recalibrate_depth' sent.\nResponse: {response.text}")
                QTimer.singleShot(500, self.manual_refresh_status) # Refresh status
            else:
                QMessageBox.warning(self, "Command Error", f"Server for /recalibrate_depth: {response.status_code}: {response.text}")
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Command '/recalibrate_depth' error: {str(e)}")
            traceback.print_exc()

    def get_active_ip_address(self):
        # Attempt to find a non-localhost IP. This is a common heuristic.
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)
            s.connect(('10.254.254.254', 1)) # Doesn't have to be reachable
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1' # Fallback
        finally:
            s.close()
        return ip

    def _send_parameter_update(self, endpoint, params, success_msg, error_title):
        if not self.float_ip: QMessageBox.warning(self, "Error", "Float IP not set."); return
        try:
            url = f"http://{self.float_ip}{endpoint}"
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200: QMessageBox.information(self, "Success", success_msg); QTimer.singleShot(500, self.manual_refresh_status)
            else: QMessageBox.warning(self, "Error", f"Failed to update: {response.text}")
        except Exception as e: QMessageBox.critical(self, "Error", f"Error {error_title}: {str(e)}"); traceback.print_exc()
        finally: self.editing_fields = False

    def set_target_depth(self): self._send_parameter_update("/set_target_depth", {'depth': self.target_depth_input.value()}, "Target depth updated", "setting target depth")
    def set_wait_time(self): self._send_parameter_update("/set_wait_time", {'seconds': self.wait_time_input.value()}, "Wait time updated", "setting wait time")
    def set_company_number(self): self._send_parameter_update("/set_company_number", {'value': self.company_number_input.value()}, "Company number updated", "setting company number")

    # save_to_coordinates_json can be adapted if needed for the new self.logged_data_points structure

    def closeEvent(self, event):
        print("Closing FloatController...")
        if self.capturing_data: self.stop_capture()
        
        if self.status_worker and self.status_worker.isRunning():
            print("Stopping status worker...")
            self.status_worker.stop()
            self.status_worker.wait(1000)
        
        if self.data_receiver_thread and self.data_receiver_thread.isRunning():
            print("Stopping data receiver thread...")
            self.data_receiver_thread.stop_server() # Use the new method
            # self.data_receiver_thread.wait(2000) # stop_server now includes wait

        self.auto_update_timer.stop()
        self.local_time_timer.stop()
        print("FloatController closed.")
        super().closeEvent(event)