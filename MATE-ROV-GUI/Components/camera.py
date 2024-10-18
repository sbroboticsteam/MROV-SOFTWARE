from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QVBoxLayout, QLabel 
from PyQt5.QtCore import QUrl, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage
import cv2
import os

class Webcam(QWidget):
    def __init__(self):
        super(Webcam, self).__init__()

        self.layout = QVBoxLayout()
        
        self.feedLabel = QLabel()
        self.layout.addWidget(self.feedLabel)
        
        self.cancelBtn = QPushButton("No")
        self.cancelBtn.clicked.connect(self.cancel)
        self.layout.addWidget(self.cancelBtn)

        self.worker1 = Worker1()
        self.worker1.imageUpdate.connect(self.imageUpdateSlot)
        self.worker1.start()
        
        self.setLayout(self.layout)
    def imageUpdateSlot(self, img):
        self.feedLabel.setPixmap(QPixmap.fromImage(img))

    def cancel(self):
        self.worker1.stop()
class Worker1(QThread):
    imageUpdate = pyqtSignal(QImage)
    def run(self):
        self.threadActive = True
        cam = cv2.VideoCapture(0)
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