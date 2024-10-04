from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QVBoxLayout, QSlider, QHBoxLayout, QLabel, QProgressBar
import sys

# each "component" in PyQt5 is a class
class MainWindow(QMainWindow): # MainWindow class extends QMainWindow
    def __init__(self):
        super().__init__() # initialize class
        self.setWindowTitle("Controller Sensitivity")
        layout = QHBoxLayout() # QVBoxLayout is used to construct vertical components (i.e. elements are stacked on top of each other)
        slider = QSlider()
        label = QLabel()
        joystick_label = QSlider

        


        name = QLabel("Controller Sensitivity")

        

        # Create labels and sliders
        joystick_label = QLabel("Joystick")
        joystick_slider = QSlider(Qt.Horizontal)
        button_label = QLabel("Button")
        button_slider = QSlider(Qt.Horizontal)

        # Add widget
        layout.addWidget(joystick_label) # layout.addWidget adds a widget to the layout
        layout.addWidget(joystick_slider)
        layout.addWidget(button_label)
        layout.addWidget(button_slider)

        # Set slider properties
        joystick_slider.setMinimum(1)
        joystick_slider.setMaximum(100)
        button_slider.setMinimum(1)
        button_slider.setMaximum(100)

        # Set main layout for the window
        self.setLayout(layout)


        

        central = QWidget() # create separate widget to act as a central widget (container) for the rest of the widgets
        central.setLayout(layout) # set the layout for this central widget to the layout we previously defined
        self.setCentralWidget(central) # set central widget for MainWindow (makes this widget the main content area)

controller_sensitivity = QApplication(sys.argv) # required to be called once for every PyQt5 app

window = MainWindow() # create instance of MainWindow
window.show() # show the main window (make it visible)

controller_sensitivity.exec() # starts application event loop (keeps app running continuously until we exit)