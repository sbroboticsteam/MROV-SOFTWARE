from PyQt5.QtWidgets import QWidget, QPushButton, QVBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize, QMutex, QMutexLocker
from PyQt5.QtGui import QPixmap, QImage, QResizeEvent, QColor
import cv2
import os
import time

# Remove global rtsp_url
# rtsp_url='http://localhost:3000/video'


class Webcam(QWidget):
    # Accept port and encoding instead of a single URL
    def __init__(self, port, encoding='H264'): # Default to H264
        super(Webcam, self).__init__()
        self.port = port
        self.encoding = encoding

        self.layout = QVBoxLayout()

        self.feedLabel = QLabel()
        self.feedLabel.setAlignment(Qt.AlignCenter)
        self.feedLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addWidget(self.feedLabel)

        placeholder = QPixmap(640, 480)
        placeholder.fill(QColor(0, 0, 0))
        self.feedLabel.setPixmap(placeholder)

        button_layout = QVBoxLayout() # This layout wasn't used, removing addLayout later

        self.startBtn = QPushButton("Start")
        self.startBtn.clicked.connect(self.start)
        self.startBtn.setStyleSheet("QPushButton { color: gray; }")
        self.layout.addWidget(self.startBtn)

        self.cancelBtn = QPushButton("Stop")
        self.cancelBtn.clicked.connect(self.cancel)
        self.cancelBtn.setStyleSheet("QPushButton { color: gray; }")
        self.layout.addWidget(self.cancelBtn)

        # Removed self.layout.addLayout(button_layout) as it wasn't populated

        self.mutex = QMutex()
        self.current_image = None
        self.is_visible = True
        self.aspect_ratio = 4 / 3 # Default, will be updated

        # Instantiate the new GStreamerWorker
        self.worker = GStreamerWorker(self.port, self.encoding)
        self.worker.imageUpdate.connect(self.imageUpdateSlot)
        self.worker.statusUpdate.connect(self.handleStatusUpdate) # Optional: Handle status messages
        self.worker.start()

        self.updateButtonStyles(True) # Assume starting initially

        self.setLayout(self.layout)

    def handleStatusUpdate(self, message):
        # Optional: Display status messages somewhere, e.g., in a status bar or print
        print(f"[{self.port} - {self.encoding}]: {message}")

    def updateButtonStyles(self, isRunning):
        """Update button colors based on whether the stream is running"""
        if isRunning:
            self.startBtn.setStyleSheet("QPushButton { color: gray; }")
            self.startBtn.setEnabled(False) # Disable start when running
            self.cancelBtn.setStyleSheet("QPushButton { color: red; font-weight: bold; }")
            self.cancelBtn.setEnabled(True) # Enable stop when running
        else:
            self.startBtn.setStyleSheet("QPushButton { color: green; font-weight: bold; }")
            self.startBtn.setEnabled(True) # Enable start when stopped
            self.cancelBtn.setStyleSheet("QPushButton { color: gray; }")
            self.cancelBtn.setEnabled(False) # Disable stop when stopped

    def imageUpdateSlot(self, img):
        if not self.is_visible:
            return
        try:
            with QMutexLocker(self.mutex):
                # Check if received image is valid before processing
                if img is None or img.isNull():
                     print(f"[{self.port}] Received invalid image")
                     return
                self.current_image = img
                # Update aspect ratio only if it hasn't been set or is default
                if self.aspect_ratio == 4/3 and img.height() > 0:
                    self.aspect_ratio = img.width() / img.height()

            # Check label dimensions before scaling
            if self.feedLabel.width() > 0 and self.feedLabel.height() > 0:
                try:
                    # Scale image while keeping aspect ratio
                    scaled_img = img.scaled(
                        self.feedLabel.size(), # Use label's QSize
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation # Use smooth scaling
                        )
                    self.feedLabel.setPixmap(QPixmap.fromImage(scaled_img))
                except Exception as e:
                    print(f"[{self.port}] Error scaling image: {e}")
            # else: # Optional: Handle case where label size is zero?
            #     self.feedLabel.setPixmap(QPixmap.fromImage(img)) # Show original if not scaled

        except Exception as e:
            print(f"[{self.port}] Error in imageUpdateSlot: {e}")

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if not self.isVisible():
            return
        try:
            with QMutexLocker(self.mutex):
                if self.current_image and not self.current_image.isNull() and self.feedLabel.width() > 0 and self.feedLabel.height() > 0:
                    try:
                        scaled_img = self.current_image.scaled(
                            self.feedLabel.size(),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                        self.feedLabel.setPixmap(QPixmap.fromImage(scaled_img))
                    except Exception as e:
                        print(f"[{self.port}] Error scaling image during resize: {e}")
        except Exception as e:
            print(f"[{self.port}] Error in resizeEvent: {e}")

    def showEvent(self, event):
        self.is_visible = True
        # If worker isn't running when shown, try starting it
        if not self.worker.isRunning():
             self.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.is_visible = False
        # Consider stopping the worker when hidden to save resources
        # self.cancel() # Uncomment if you want to stop stream on hide
        super().hideEvent(event)

    def start(self):
        if not self.worker.isRunning():
            print(f"[{self.port}] Starting worker...")
            # Ensure previous worker is cleaned up if necessary (should be handled by stop/close)
            self.worker = GStreamerWorker(self.port, self.encoding)
            self.worker.imageUpdate.connect(self.imageUpdateSlot)
            self.worker.statusUpdate.connect(self.handleStatusUpdate)
            self.worker.start()
            self.updateButtonStyles(True)
        else:
             print(f"[{self.port}] Worker already running.")


    def cancel(self):
        if self.worker.isRunning():
            print(f"[{self.port}] Stopping worker...")
            self.worker.stop()
            self.updateButtonStyles(False)
            # Clear the label or show a placeholder when stopped
            placeholder = QPixmap(self.feedLabel.width(), self.feedLabel.height())
            placeholder.fill(QColor(0, 0, 0))
            self.feedLabel.setPixmap(placeholder)
            self.current_image = None # Reset current image
        else:
            print(f"[{self.port}] Worker already stopped.")


    def closeEvent(self, event):
        print(f"[{self.port}] Close event called.")
        self.cancel()
        super().closeEvent(event)

# Remove the old Worker class if it's not used elsewhere
# class Worker(QThread): ...

# Rename RTSPWorker to GStreamerWorker and modify it
class GStreamerWorker(QThread):
    imageUpdate = pyqtSignal(QImage)
    statusUpdate = pyqtSignal(str)

    def __init__(self, port, encoding='H264'):
        super(GStreamerWorker, self).__init__()
        self.port = port
        self.encoding = encoding.upper() # Ensure uppercase for comparison
        self.threadActive = False
        self.pipeline_str = self._build_pipeline()

    def _build_pipeline(self):
        """Builds the GStreamer pipeline string for cv2.VideoCapture"""
        if self.encoding == 'H264':
            caps = "application/x-rtp,media=video,clock-rate=90000,encoding-name=H264,payload=96"
            pipeline = (
                f"udpsrc port={self.port} caps=\"{caps}\" ! "
                # Match latency and drop-on-latency from multistream.bat
                "rtpjitterbuffer latency=0 drop-on-latency=true ! " 
                "rtph264depay ! h264parse ! avdec_h264 ! " 
                "videoconvert ! video/x-raw,format=BGR ! " # Convert to BGR for OpenCV
                # appsink is required for OpenCV, sync=false matches multistream.bat's autovideosink setting
                "appsink drop=true sync=false" 
            )
        elif self.encoding == 'JPEG':
            caps = "application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26"
            pipeline = (
                f"udpsrc port={self.port} caps=\"{caps}\" ! "
                # Match latency and drop-on-latency from multistream.bat
                "rtpjitterbuffer latency=0 drop-on-latency=true ! " 
                "rtpjpegdepay ! jpegdec ! " 
                "videoconvert ! video/x-raw,format=BGR ! " # Convert to BGR for OpenCV
                # appsink is required for OpenCV, sync=false matches multistream.bat's autovideosink setting
                "appsink drop=true sync=false"
            )
        else:
            self.statusUpdate.emit(f"Unsupported encoding: {self.encoding}")
            return None
        return pipeline

    def run(self):
        self.threadActive = True
        if not self.pipeline_str:
            self.statusUpdate.emit("Pipeline creation failed.")
            self.threadActive = False
            return

        self.statusUpdate.emit(f"Connecting to UDP port {self.port}...")
        print(f"Using pipeline: {self.pipeline_str}") # Debug print

        # Use cv2.CAP_GSTREAMER flag
        cam = cv2.VideoCapture(self.pipeline_str, cv2.CAP_GSTREAMER)

        if not cam.isOpened():
            self.statusUpdate.emit(f"Failed to open GStreamer pipeline on port {self.port}")
            self.threadActive = False
            return # Exit if pipeline fails to open

        self.statusUpdate.emit(f"Pipeline opened successfully on port {self.port}")

        while self.threadActive:
            try:
                ret, frame = cam.read()
                if ret:
                    # Frame is already BGR due to pipeline configuration
                    # Convert BGR to RGB for QImage
                    rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_image.shape
                    bytes_per_line = ch * w
                    qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
                    self.imageUpdate.emit(qt_image)
                else:
                    # Failed to grab frame, could be temporary or end of stream
                    self.statusUpdate.emit(f"Failed to grab frame from port {self.port}. Retrying...")
                    # Add a small delay to prevent busy-waiting if the stream is truly down
                    time.sleep(0.1)
                    # Optional: Try reopening the capture if it consistently fails
                    # if not cam.isOpened():
                    #    cam.release()
                    #    cam = cv2.VideoCapture(self.pipeline_str, cv2.CAP_GSTREAMER)
                    #    if not cam.isOpened():
                    #        self.statusUpdate.emit(f"Failed to reopen pipeline on port {self.port}. Stopping.")
                    #        self.threadActive = False


            except Exception as e:
                self.statusUpdate.emit(f"Error in GStreamerWorker loop: {e}")
                time.sleep(0.5) # Wait a bit after an error

        # Clean up
        self.statusUpdate.emit(f"Releasing camera capture on port {self.port}")
        if cam.isOpened():
            cam.release()
        self.statusUpdate.emit(f"Worker thread finished for port {self.port}")

    def stop(self):
        self.statusUpdate.emit(f"Stop requested for port {self.port}")
        self.threadActive = False
        # No need to explicitly quit/wait if the loop condition handles it
        # self.quit()
        # self.wait() # Wait might block if the loop is stuck, rely on threadActive
