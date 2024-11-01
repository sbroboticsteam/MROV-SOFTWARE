from PyQt5.QtWidgets import QWidget, QPushButton, QVBoxLayout, QLabel 
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage
import cv2
import os


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

        self.worker = Worker(0)
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