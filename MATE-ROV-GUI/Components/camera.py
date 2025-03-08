from PyQt5.QtWidgets import QWidget, QPushButton, QVBoxLayout, QLabel 
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage
import cv2
import os

# rtsp_url='rtsp://admin:admin@192.168.1.198/media/video1'
rtsp_url='http://localhost:3000/video'


class Webcam(QWidget):
    def __init__(self):
        super(Webcam, self).__init__()

        self.layout = QVBoxLayout()
        
        self.feedLabel = QLabel()
        self.layout.addWidget(self.feedLabel)
        
        self.startBtn = QPushButton("Yes")
        self.startBtn.clicked.connect(self.start)
        self.layout.addWidget(self.startBtn)

        self.cancelBtn = QPushButton("No")
        self.cancelBtn.clicked.connect(self.cancel)
        self.layout.addWidget(self.cancelBtn)

        self.worker = RTSPWorker(rtsp_url)
        self.worker.imageUpdate.connect(self.imageUpdateSlot)
        self.worker.start()
        
        self.setLayout(self.layout)
    def imageUpdateSlot(self, img):
        self.feedLabel.setPixmap(QPixmap.fromImage(img))
    def start(self):
        if (not self.worker.isRunning()):
            self.worker.start()
    def cancel(self):
        if (self.worker.isRunning()):
            self.worker.stop()
class Worker(QThread):
    imageUpdate = pyqtSignal(QImage)
    def __init__(self, camera):
        super(Worker, self).__init__()
        self.camera = camera
    def run(self):
        self.threadActive = True
        cam = cv2.VideoCapture(self.camera)
        while self.threadActive:
            ret, frame = cam.read()
            if ret:
                image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                flipped = cv2.flip(image, 1)
                toQt = QImage(flipped.data, flipped.shape[1], flipped.shape[0], QImage.Format_RGB888)
                self.imageUpdate.emit(toQt)
    def stop(self):
        self.threadActive = False
        self.quit()
class RTSPWorker(QThread):
    imageUpdate=pyqtSignal(QImage)
    statusUpdate=pyqtSignal(str)
    def __init__(self, rtsp_url):
        super(RTSPWorker, self).__init__()
        self.rtsp_url = rtsp_url
        self.threadActive = False
    
    def run(self):
        self.threadActive = True
        self.statusUpdate.emit("Connecting to RTSP stream...")
        
        # Open the RTSP stream
        cam = cv2.VideoCapture(self.rtsp_url)
        
        if cam.isOpened():
            self.statusUpdate.emit("Connected to stream")
            
            # Configure for low latency
            cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            while self.threadActive:
                ret, frame = cam.read()
                if ret:
                    # Convert to RGB for Qt
                    image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = image.shape
                    bytes_per_line = ch * w
                    
                    # Convert to QImage
                    qt_image = QImage(image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    
                    # Emit the image
                    self.imageUpdate.emit(qt_image)
                else:
                    # Handle frame read failure
                    self.statusUpdate.emit("Failed to read frame")
                    # Try to reconnect if connection is lost
                    cam.release()
                    cam = cv2.VideoCapture(self.rtsp_url)
                    if not cam.isOpened():
                        self.statusUpdate.emit("Connection lost")
                        break
        else:
            self.statusUpdate.emit("Failed to connect to stream")
        
        # Clean up
        if cam.isOpened():
            cam.release()
    
    def stop(self):
        self.threadActive = False
        self.quit()