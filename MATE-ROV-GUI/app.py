from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QVBoxLayout, QLayout
from Components.camera import Webcam
from Components.temp_camera import Camera
from Components.adjustable import AdjustableWidget


import sys


# each "component" in PyQt5 is a class
class MainWindow(QMainWindow): # MainWindow class extends QMainWindow
    def __init__(self):
        super().__init__() # initialize class
        self.setWindowTitle("MATE ROV Dashboard") # setting the window title (what appears at the top of the window)



       
        self.cam = AdjustableWidget("Webcam", self)        
        self.cam.setGeometry(100, 100, 900, 700)
        

        self.sp = AdjustableWidget("Speed Panel", self)
        self.sp.setGeometry(1000,100,350,250)
        


    
        self.setFixedWidth(1700)
        self.setFixedHeight(1500)


app = QApplication(sys.argv) # required to be called once for every PyQt5 app


window = MainWindow() # create instance of MainWindow
window.show() # show the main window (make it visible)


app.exec() # starts application event loop (keeps app running continuously until we exit)
