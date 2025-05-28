import sys
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstVideo
from PyQt5 import QtWidgets, QtCore
import os
from Components.camera_config import CameraConfig
from Components.camera import VideoWidget, CameraStream

class USB1CameraWindow(QtWidgets.QMainWindow):
    """Widget for displaying the first USB camera feed"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("USB Camera 1")
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(main_widget)
        
        # Get the pipeline from configuration
        config = CameraConfig()
        pipeline = config.get_gstreamer_pipeline("usb0")
        
        # Create the camera stream
        self.camera = CameraStream(pipeline, "USB Camera 1")
        layout.addWidget(self.camera)
        
        self.setCentralWidget(main_widget)
    
    def closeEvent(self, event):
        try:
            self.camera.close()
        except:
            pass
        super().closeEvent(event)

class USB2CameraWindow(QtWidgets.QMainWindow):
    """Widget for displaying the second USB camera feed"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("USB Camera 2")
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(main_widget)
        
        # Get the pipeline from configuration
        config = CameraConfig()
        pipeline = config.get_gstreamer_pipeline("usb2")
        
        # Create the camera stream
        self.camera = CameraStream(pipeline, "USB Camera 2")
        layout.addWidget(self.camera)
        
        self.setCentralWidget(main_widget)
    
    def closeEvent(self, event):
        try:
            self.camera.close()
        except:
            pass
        super().closeEvent(event)

class ZEDCameraWindow(QtWidgets.QMainWindow):
    """Widget for displaying the ZED camera feed"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZED Camera")
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(main_widget)
        
        # Get the pipeline from configuration
        config = CameraConfig()
        pipeline = config.get_gstreamer_pipeline("zed")
        
        # Create the camera stream
        self.camera = CameraStream(pipeline, "ZED Camera")
        layout.addWidget(self.camera)
        
        self.setCentralWidget(main_widget)
    
    def closeEvent(self, event):
        try:
            self.camera.close()
        except:
            pass
        super().closeEvent(event)