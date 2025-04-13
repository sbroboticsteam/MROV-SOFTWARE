from PyQt5.QtWidgets import QWidget, QPushButton, QVBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize, QMutex, QMutexLocker
from PyQt5.QtGui import QPixmap, QImage, QResizeEvent, QColor
import cv2
import os
import time

rtsp_url='rtsp://admin:admin@192.168.1.198/media/video1?tcp'
# rtsp_url='http://localhost:3000/video'


class Webcam(QWidget):
    def __init__(self):
        super(Webcam, self).__init__()

        self.layout = QVBoxLayout()
        
        self.feedLabel = QLabel()
        self.feedLabel.setAlignment(Qt.AlignCenter)         
        self.feedLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # self.feedLabel.setMinimumSize(QSize(320, 240))
        self.layout.addWidget(self.feedLabel)
        
        # Create a placeholder pixmap with the full size to prevent resizing
        placeholder = QPixmap(640, 480)
        placeholder.fill(QColor(0, 0, 0))  # Fill with black
        self.feedLabel.setPixmap(placeholder)

        button_layout = QVBoxLayout()

        # Create Start button with initial style
        self.startBtn = QPushButton("Start")
        self.startBtn.clicked.connect(self.start)
        self.startBtn.setStyleSheet("QPushButton { color: gray; }")
        self.layout.addWidget(self.startBtn)

        # Create Stop button with initial style
        self.cancelBtn = QPushButton("Stop")
        self.cancelBtn.clicked.connect(self.cancel)
        self.cancelBtn.setStyleSheet("QPushButton { color: gray; }")
        self.layout.addWidget(self.cancelBtn)

        self.layout.addLayout(button_layout)

        self.mutex = QMutex()
        self.current_image = None
        self.is_visible = True
        self.aspect_ratio = 4 / 3

        self.worker = RTSPWorker(rtsp_url)
        self.worker.imageUpdate.connect(self.imageUpdateSlot)
        self.worker.start()
        
        # Set initial button states since the worker is already started
        self.updateButtonStyles(True)
        
        self.setLayout(self.layout)

    def updateButtonStyles(self, isRunning):
        """Update button colors based on whether the stream is running"""
        if isRunning:
            # Stream is running - Start button is inactive, Stop button is active
            self.startBtn.setStyleSheet("QPushButton { color: gray; }")
            self.cancelBtn.setStyleSheet("QPushButton { color: red; font-weight: bold; }")
        else:
            # Stream is stopped - Start button is active, Stop button is inactive
            self.startBtn.setStyleSheet("QPushButton { color: green; font-weight: bold; }")
            self.cancelBtn.setStyleSheet("QPushButton { color: gray; }")

    def imageUpdateSlot(self, img):
        if not self.is_visible:
            return
        try:     
            with QMutexLocker(self.mutex):
                self.current_image = img
                if self.aspect_ratio == 4/3:
                    self.aspect_ratio = img.width() / img.height()
            if self.feedLabel.width() > 0 and self.feedLabel.height() > 0:
                try:
                    scaled_img = img.scaled(
                        self.feedLabel.width(), 
                        self.feedLabel.height(), 
                        Qt.KeepAspectRatio
                        )
                    self.feedLabel.setPixmap(QPixmap.fromImage(scaled_img))
                except Exception as e:
                    print(f"Error scaling image: {e}")
        except Exception as e:
            print(f"Error in imageUpdateSlot: {e}")
    def resizeEvent(self, event: QResizeEvent):
        # When widget is resized, update the image display
        super().resizeEvent(event)

        # Don't try to update if we're minimized or hidden
        if not self.isVisible():
            return
            
        try:
            with QMutexLocker(self.mutex):
                if self.current_image and self.feedLabel.width() > 0 and self.feedLabel.height() > 0:
                    try:
                        scaled_img = self.current_image.scaled(
                            self.feedLabel.width(),
                            self.feedLabel.height(),
                            Qt.KeepAspectRatio
                        )
                        self.feedLabel.setPixmap(QPixmap.fromImage(scaled_img))
                    except Exception as e:
                        print(f"Error scaling image during resize: {e}")
        except Exception as e:
            print(f"Error in resizeEvent: {e}")
    def showEvent(self, event):
        # Widget is becoming visible
        self.is_visible = True
        super().showEvent(event)
        
    def hideEvent(self, event):
        # Widget is becoming invisible
        self.is_visible = False
        super().hideEvent(event)
    def start(self):
        if (not self.worker.isRunning()):
            self.worker = RTSPWorker(rtsp_url)  # Create a new worker if needed
            self.worker.imageUpdate.connect(self.imageUpdateSlot)
            self.worker.start()
            # Update button styles
            self.updateButtonStyles(True)

    def cancel(self):
        if (self.worker.isRunning()):
            self.worker.stop()
            # Update button styles
            self.updateButtonStyles(False)

    def closeEvent(self, event):
        # Properly clean up when the widget is closed
        self.cancel()
        super().closeEvent(event)
class Worker(QThread):
    imageUpdate = pyqtSignal(QImage)
    def __init__(self, camera):
        super(Worker, self).__init__()
        self.camera = camera
        self.threadActive = False
    def run(self):
        self.threadActive = True
        cam = cv2.VideoCapture(self.camera)
        while self.threadActive:
            try:
                ret, frame = cam.read()
                if ret:
                    image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    flipped = cv2.flip(image, 1)
                    toQt = QImage(flipped.data, flipped.shape[1], flipped.shape[0], flipped.shape[1]*3, QImage.Format_RGB888)
                    toQt = toQt.copy()  # Make a deep copy to ensure memory safety
                    self.imageUpdate.emit(toQt)
                else:
                    time.sleep(0.1)
            except Exception as e:
                print(f"Error in Worker thread: {e}")
                time.sleep(0.1)
        cam.release()
    def stop(self):
        self.threadActive = False
        self.quit()
        self.wait()
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

            retry_count = 0
            max_retries = 5
            
            while self.threadActive:
                try:
                    ret, frame = cam.read()
                    if ret:
                        # Convert to RGB for Qt
                        retry_count = 0
                        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        h, w, ch = image.shape
                        bytes_per_line = ch * w
                        
                        # Convert to QImage
                        qt_image = QImage(image.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
                        
                        # Emit the image
                        self.imageUpdate.emit(qt_image)
                    else:
                        # Handle frame read failure with retries
                        retry_count += 1
                        if retry_count > max_retries:
                            self.statusUpdate.emit("Failed to read frame, reconnecting...")
                            cam.release()
                            time.sleep(1)  # Wait before reconnecting
                            cam = cv2.VideoCapture(self.rtsp_url)
                            retry_count = 0
                        time.sleep(0.1)
                except Exception as e:
                    self.statusUpdate.emit(f"Error: {str(e)}")
                    time.sleep(1)
                    try:
                        cam.release()
                        cam = cv2.VideoCapture(self.rtsp_url)
                    except:
                        pass
        else:
            self.statusUpdate.emit("Failed to connect to stream")
        
        # Clean up
        if cam.isOpened():
            cam.release()
    
    def stop(self):
        self.threadActive = False
        self.quit()
        self.wait()