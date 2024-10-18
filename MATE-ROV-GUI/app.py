from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QVBoxLayout
from Components.camera import Webcam
from Components.temp_camera import Camera

import sys

# each "component" in PyQt5 is a class
class MainWindow(QMainWindow): # MainWindow class extends QMainWindow
    def __init__(self):
        super().__init__() # initialize class
        self.setWindowTitle("MATE ROV Dashboard") # setting the window title (what appears at the top of the window)
        layout = QVBoxLayout() # QVBoxLayout is used to construct vertical components (i.e. elements are stacked on top of each other)
        button = QPushButton("Underwater robot go brrr") # QPushButton creates a button that can be clicked
        layout.addWidget(button) # layout.addWidget adds a widget to the layout

        component = Camera() # declaring a new instance of Component()
        layout.addWidget(component) # adding component to widget (this will appear below the button we declared earlier)

        central = QWidget() # create separate widget to act as a central widget (container) for the rest of the widgets
        central.setLayout(layout) # set the layout for this central widget to the layout we previously defined
        self.setCentralWidget(central) # set central widget for MainWindow (makes this widget the main content area)

app = QApplication(sys.argv) # required to be called once for every PyQt5 app

window = MainWindow() # create instance of MainWindow
window.show() # show the main window (make it visible)

app.exec() # starts application event loop (keeps app running continuously until we exit)