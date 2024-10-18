from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QVBoxLayout, QGridLayout
# from Components.component import Component
from Components.speedpanel import SpeedPanel
from Components.camera import Webcam
from Components.connectivity import Connectivity
from Components.controller_sensitivity import ControllerSensitivity, AdjustableControllerSensivitity
from Components.adjustable import AdjustableWidget

import sys

# each "component" in PyQt5 is a class
class MainWindow(QMainWindow): # MainWindow class extends QMainWindow
    def __init__(self):
        super().__init__() # initialize class
        self.setWindowTitle("MATE ROV Dashboard") # setting the window title (what appears at the top of the window)
        grid_layout = QGridLayout() # QGridLayout is used to create grid layouts

        speed_panel = SpeedPanel()
        speed_panel.update_speeds(50, 75, 100)

        webcam = Webcam()
        connectivity = Connectivity()
        controllersensitivity = ControllerSensitivity()

        test_adjustable = AdjustableWidget()
        # test_adjustable2 = AdjustableControllerSensivitity()
        
        # grid layout: 0, 0 | 0, 1
        #              -----------
        #              1, 0 | 1, 1
        grid_layout.addWidget(webcam, 0, 0)
        grid_layout.addWidget(connectivity, 0, 1)
        grid_layout.addWidget(controllersensitivity, 1, 0)
        grid_layout.addWidget(speed_panel, 1, 1)
        grid_layout.addWidget(test_adjustable, 2, 0)
        # grid_layout.addWidget(test_adjustable2, 2, 1)

        central = QWidget() # create separate widget to act as a central widget (container) for the rest of the widgets
        central.setLayout(grid_layout) # set the layout for this central widget to the layout we previously defined
        self.setCentralWidget(central) # set central widget for MainWindow (makes this widget the main content area)

app = QApplication(sys.argv) # required to be called once for every PyQt5 app

window = MainWindow() # create instance of MainWindow
window.show() # show the main window (make it visible)

app.exec() # starts application event loop (keeps app running continuously until we exit)