from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QVBoxLayout, QLayout, QHBoxLayout, QComboBox, QStackedWidget, QMessageBox
from Components.camera import MainWindow as CameraWindow
# from Components.temp_camera import Camera
#from Components.network import NetworkConnectionWidget
from Components.adjustable import AdjustableWidget
import os, subprocess
from PyQt5.QtCore import QThread, pyqtSignal
from Components.data_handler import DataHandler
import sys

from Components.controller import ControllerSender  # Add this import

class DashboardPage(QWidget):
    def __init__(self, parent=None, data_handler=None):
        super().__init__(parent)
        self.widgets=[]
        self.data_handler = data_handler
        self.setStyleSheet('background-color: #f0f0f0;')
        print(f"DashboardPage received data_handler: {self.data_handler}")

    def addWidget(self, widget_type):
        widget=AdjustableWidget(widget_type, self)
        if widget_type=="Webcam":
            widget.setGeometry(100, 100, 900, 700)
        elif widget_type=="Speed Panel":
            widget.setGeometry(1000, 100, 350, 250)
        elif widget_type=="Depth-Time Graph":
            widget.setGeometry(100, 800, 600, 400)
        elif widget_type=="Connectivity":
            widget.setGeometry(1000, 400, 350, 250)
        elif widget_type=="Controller Sensitivity":
            widget.setGeometry(1000, 700, 350, 250)
        elif widget_type=="Controller Sender": 
            widget.setGeometry(1000, 700, 400, 300)
        elif widget_type=="Leak Sensor": 
            widget.setGeometry(400, 350, 300, 200)
        # elif widget_type=="Network Connection":
        #     widget.setGeometry(1000, 950, 350, 250)

        self.widgets.append(widget)
        widget.show()


class DashboardHeader(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()
    
    def setupUI(self):
        layout=QHBoxLayout()
        layout.setContentsMargins(10,5,10,5)

        self.page_selector=QComboBox()
        self.page_selector.setStyleSheet("""
                QComboBox {
                    background-color: white;
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    padding: 5px;
                    min-width: 100px;
                }""")
        
        self.widget_selector=QComboBox()
        self.widget_selector.setStyleSheet("""
                QComboBox {
                    background-color: white;
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    padding: 5px;
                    min-width: 150px;
                }""")

        self.add_page_btn=QPushButton('+ New Page')
        self.add_page_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    padding: 5px 10px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }""")

        self.script_selector=QComboBox()
        self.script_selector.setStyleSheet("""
                QComboBox {
                    background-color: white;
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    padding: 5px;
                    min-width: 200px;
                }""")
        
        self.run_script_btn=QPushButton('Run Script')
        self.run_script_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    padding: 5px 10px;
                }
                QPushButton:hover {
                    background-color: #0b7dda;
                }""")
        
        layout.addWidget(self.page_selector)
        layout.addWidget(self.add_page_btn)
        layout.addStretch()
        layout.addWidget(self.script_selector)
        layout.addWidget(self.run_script_btn)
        layout.addWidget(self.widget_selector)

        self.setLayout(layout)
        self.setFixedHeight(50)
        self.setStyleSheet('background-color: #333333;')

class ScriptExecutionThread(QThread):
    finished = pyqtSignal(int)
    error = pyqtSignal(str)
    
    def __init__(self, script_path):
        super().__init__()
        self.script_path = script_path
        
    def run(self):
        try:
            result = subprocess.run(
                [sys.executable, self.script_path], 
                capture_output=True, 
                text=True
            )
            self.finished.emit(result.returncode)
            if result.stderr:
                self.error.emit(result.stderr)
        except Exception as e:
            self.error.emit(str(e))

# each "component" in PyQt5 is a class
class MainWindow(QMainWindow): # MainWindow class extends QMainWindow
    def __init__(self):
        super().__init__() # initialize class
        self.script_thread=None
        self.data_handler = DataHandler(port = 8001)  # Initialize data handler
        print(f"MainWindow created data_handler: {self.data_handler}")
        self.data_handler.start()  # Start the data handler thread
        self.setWindowTitle("MATE ROV Dashboard") # setting the window title (what appears at the top of the window)
        self.setupUI()
        self.showMaximized() # show the window maximized (full screen)


        # NO LONGER NECESSARY TO MANUALLY ADD WIDGETS LIKE CAVEMEN!!!!
        # self.cam = AdjustableWidget("Webcam", self)        
        # self.cam.setGeometry(100, 100, 900, 700)
        

        # self.sp = AdjustableWidget("Speed Panel", self)
        # self.sp.setGeometry(1000,100,350,250)
        
        # self.dt=AdjustableWidget("Depth-Time Graph", self)
        # self.dt.setGeometry(100, 800, 600, 400)


    
        # self.setFixedWidth(1700)
        # self.setFixedHeight(1500)
    
    def setupUI(self):
        central=QWidget()
        self.setCentralWidget(central)
        layout=QVBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)

        self.header=DashboardHeader()
        layout.addWidget(self.header)

        self.pages=QStackedWidget()
        layout.addWidget(self.pages)

        self.widgets_list=[
            #"Webcam",
            # "CSI 1", # our 3 camera feeds, adjust later
            # "CSI 2",
            # Update the list to include individual cameras
            #"USB Camera",   # Keep the combined view
            "USB Camera 1", # Individual USB camera 1
            "USB Camera 2", # Individual USB camera 2
            "ZED Camera",   # ZED camera
            "360 Camera",  # Add 360 camera
            "Interactive 360° Camera",
            "Endoscope",
            "Controller Sensitivity",
            # "Auto Mode",
            "Connectivity",
            "Speed Panel",
            "Depth-Time Graph",
            'Network Connection',
            "Controller Sender",
            "Leak Sensor"
        ]
        self.header.widget_selector.addItems(self.widgets_list)

        self.populate_script_selector()

        self.header.add_page_btn.clicked.connect(self.addNewPage)
        self.header.page_selector.currentIndexChanged.connect(self.changePage)
        self.header.widget_selector.currentIndexChanged.connect(self.addWidgetToCurrent)
        self.header.run_script_btn.clicked.connect(self.run_selected_script)
        
        self.addNewPage()

    def addNewPage(self):
        page_num = self.pages.count() + 1
        new_page = DashboardPage(data_handler=self.data_handler)
        self.pages.addWidget(new_page)
        self.header.page_selector.addItem(f"Page {page_num}")
        self.header.page_selector.setCurrentIndex(self.pages.count() - 1)
        
    def changePage(self, index):
        if index >= 0:
            self.pages.setCurrentIndex(index)
            
    def addWidgetToCurrent(self, index):
        widget_name = self.header.widget_selector.itemText(index)
        print(f"DEBUG - addWidgetToCurrent: Selected {widget_name} at index {index}")
        if not widget_name:
            print("DEBUG - addWidgetToCurrent: Invalid selection, returning")
            return
        if self.pages.count() > 0:
            current_page = self.pages.currentWidget()
            widget_type = self.widgets_list[index]
            print(f"DEBUG - addWidgetToCurrent: Creating widget of type {widget_type}")
            current_page.addWidget(widget_type)
        self.header.widget_selector.setCurrentIndex(0)  # Reset selection
    
    def populate_script_selector(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # put all scripts in the Scripts folder
        scripts_dir = os.path.join(current_dir, "Scripts")

        python_files = []
    
        # Check main Scripts directory
        for f in os.listdir(scripts_dir):
            if f.endswith('.py'):
                python_files.append(f"Scripts/{f}")
        
        if python_files:
            self.header.script_selector.addItems(python_files)
        else:
            self.header.script_selector.addItem("No scripts found")
        
    def run_selected_script(self):
        if self.script_thread and self.script_thread.isRunning():
            QMessageBox.warning(self, "Script Running", "A script is already running. Please wait for it to finish.")
            return
            
        script_name = self.header.script_selector.currentText()
        if not script_name:
            return
            
        current_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(current_dir, script_name)
        
        if not os.path.exists(script_path):
            QMessageBox.critical(self, "Error", f"Script file not found: {script_path}")
            return

        # Set button to indicate script is running
        self.header.run_script_btn.setText("Running...")
        self.header.run_script_btn.setEnabled(False)
        
        # Run script in a separate thread
        self.script_thread = ScriptExecutionThread(script_path)
        self.script_thread.finished.connect(self.on_script_finished)
        self.script_thread.error.connect(self.on_script_error)
        self.script_thread.start()
    
    def on_script_finished(self, return_code):
        self.header.run_script_btn.setText("Run Script")
        self.header.run_script_btn.setEnabled(True)
        
        if return_code == 0:
            QMessageBox.information(self, "Success", "Script executed successfully")
        else:
            QMessageBox.warning(self, "Warning", f"Script finished with return code: {return_code}")
            
    def on_script_error(self, error_message):
        QMessageBox.critical(self, "Error", f"Script execution error: {error_message}")
        self.header.run_script_btn.setText("Run Script")
        self.header.run_script_btn.setEnabled(True)
    
    def closeEvent(self, event):
        """Clean up resources before closing"""
        # Stop data handler thread
        if hasattr(self, 'data_handler') and self.data_handler.isRunning():
            self.data_handler.stop()
            self.data_handler.wait()
        
        # Call the original closeEvent
        super().closeEvent(event)

app = QApplication(sys.argv) # required to be called once for every PyQt5 app



window = MainWindow() # create instance of MainWindow
window.show() # show the main window (make it visible)


sys.exit(app.exec_()) # starts application event loop (keeps app running continuously until we exit)
