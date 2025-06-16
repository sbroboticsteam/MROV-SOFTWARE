import sys
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstVideo
from PyQt5 import QtWidgets, QtCore
import os
import subprocess
from Components.camera_config import CameraConfig
from Components.camera import VideoWidget, CameraStream
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QSlider, QHBoxLayout, QPushButton, QMessageBox
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect
from PyQt5.QtGui import QPainter, QPixmap, QImage, QTransform, QPen, QColor
import numpy as np
import threading

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
class Camera360Window(QtWidgets.QMainWindow):
    """Widget for displaying the 360 camera feed"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("360 Camera")
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(main_widget)
        
        config = CameraConfig()
        # This pipeline string will now include the tee and appsink from camera_config.py
        pipeline = config.get_gstreamer_pipeline("camera_360") 
        
        # CameraStream will parse this, find 'photosphere_appsink', and connect to it.
        self.camera = CameraStream(pipeline, "360 Camera") 
        layout.addWidget(self.camera)
        
        self.photosphere_button = QPushButton("Photosphere Task")
        self.photosphere_button.clicked.connect(self.handle_photosphere_task)
        layout.addWidget(self.photosphere_button) 
        
        self.setCentralWidget(main_widget)
    
    def closeEvent(self, event):
        try:
            self.camera.close()
        except:
            pass
        super().closeEvent(event)

    def handle_photosphere_task(self):
            print("DEBUG: Camera360Window - handle_photosphere_task called")
            
            if not hasattr(self.camera, 'get_latest_frame_for_photosphere'):
                QMessageBox.warning(self, "Photosphere Task Error", 
                                    "CameraStream object is missing the 'get_latest_frame_for_photosphere' method. "
                                    "Please ensure Components/camera.py is updated correctly.")
                return

            # This now calls the method in CameraStream that gets the pixmap from the appsink
            current_frame_pixmap = self.camera.get_latest_frame_for_photosphere()

            if current_frame_pixmap is None or current_frame_pixmap.isNull():
                QMessageBox.warning(self, "Photosphere Task", 
                                    "No 360° video frame available to capture from CameraStream. "
                                    "Check console for CameraStream debug messages regarding appsink.")
                return
            else:
                print("DEBUG: Camera360Window - Received valid pixmap from CameraStream.")

            # Determine project root and photospheretaskimages directory
            try:
                gui_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Components is child of MATE-ROV-GUI
                photosphere_dir = os.path.join(gui_root_dir, "photospheretaskimages")
                # print(f"DEBUG: Photosphere directory set to: {photosphere_dir}") # Already in previous version
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not determine project path: {e}")
                return

            try:
                if not os.path.exists(photosphere_dir):
                    os.makedirs(photosphere_dir)
                    # print(f"DEBUG: Created directory: {photosphere_dir}") # Already in previous version
            except OSError as e:
                QMessageBox.critical(self, "Error", f"Could not create directory {photosphere_dir}: {e}")
                return

            input_image_path = os.path.join(photosphere_dir, "input.jpg")
            output_image_path = os.path.join(photosphere_dir, "output.jpg")
            batch_script_path = os.path.join(photosphere_dir, "run_ffmpeg_photosphere.bat")

            # 1. Save current frame
            try:
                save_success = current_frame_pixmap.save(input_image_path, "JPG", 95)
                if not save_success:
                    QMessageBox.critical(self, "Error", f"Failed to save frame to {input_image_path}")
                    return
                print(f"Frame saved to {input_image_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error saving frame: {e}")
                return

            # 2. Create .bat script for FFmpeg
            ffmpeg_command = (
                f'ffmpeg -i input.jpg -vf "v360=input=dfisheye:ih_fov=195:iv_fov=195:output=equirect:out_stereo=none" -q:v 1 output.jpg -y'
            )
            
            bat_content = f"""@echo off
    setlocal
    REM This script changes its directory to where it is located.
    cd /D "%~dp0"
    echo Current directory for ffmpeg: %cd%
    echo Running FFmpeg command:
    echo {ffmpeg_command}

    {ffmpeg_command}

    if %errorlevel% neq 0 (
        echo FFmpeg command failed. Errorlevel: %errorlevel%
        exit /b 1
    )
    echo FFmpeg command successful.
    exit /b 0
    endlocal
    """
            try:
                with open(batch_script_path, "w") as f:
                    f.write(bat_content)
                print(f"Batch script created at {batch_script_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not write batch script: {e}")
                return

            # 3. Run .bat script
            try:
                print(f"Running batch script: {batch_script_path}")
                process = subprocess.run(
                    batch_script_path, 
                    shell=True, 
                    check=False,
                    capture_output=True, 
                    text=True,
                    cwd=photosphere_dir 
                )

                print("FFmpeg script stdout:")
                print(process.stdout)
                print("FFmpeg script stderr:")
                print(process.stderr)

                if process.returncode != 0:
                    QMessageBox.critical(self, "FFmpeg Error", f"FFmpeg script failed (return code {process.returncode}).\nStderr: {process.stderr}\nStdout: {process.stdout}")
                    return
                print("FFmpeg processing complete.")
            except FileNotFoundError:
                QMessageBox.critical(self, "FFmpeg Error", f"Batch script {batch_script_path} not found or ffmpeg command not found. Ensure FFmpeg is installed and in your system's PATH.")
                return
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error running FFmpeg script: {e}")
                return

            # 4. Open processed image
            if os.path.exists(output_image_path):
                try:
                    print(f"Opening {output_image_path} with default application.")
                    if sys.platform == "win32":
                        os.startfile(output_image_path)
                    elif sys.platform == "darwin":
                        subprocess.run(["open", output_image_path], check=True)
                    else: 
                        subprocess.run(["xdg-open", output_image_path], check=True)
                    QMessageBox.information(self, "Success", f"Photosphere task complete. Output image should be opening: {output_image_path}")
                except Exception as e:
                    QMessageBox.warning(self, "Image Viewer", f"Could not open image with default viewer: {e}\nImage is at: {output_image_path}")
            else:
                QMessageBox.critical(self, "Error", f"Output image {output_image_path} not found after FFmpeg processing.")


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

class Interactive360View(QWidget):
    """Interactive 360° video viewing widget with pan/tilt/zoom controls"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.StrongFocus)  # Enable keyboard focus
        
        # Initialize view parameters
        self.pan_angle = 0  # Horizontal rotation (0-360)
        self.tilt_angle = 0  # Vertical rotation (-90 to 90)
        self.zoom_level = 1.0  # Zoom level (1.0 = no zoom)
        self.pan_speed = 5  # Degrees per key press
        self.zoom_step = 0.1  # Zoom increment per key press
        
        # Image storage
        self.pixmap = None
        self.last_frame_data = None
        self.frame_width = 1920  # Default for 360 camera
        self.frame_height = 960  # Default for 360 camera
        self.buffer_lock = threading.Lock()
        
        # Initialize with a blank image
        self.pixmap = QPixmap(self.frame_width, self.frame_height)
        self.pixmap.fill(Qt.black)
        
        # Setup drag handling for mouse control
        self.dragging = False
        self.last_pos = None
    
    def set_frame(self, image):
        """Set the current frame from a QImage"""
        with self.buffer_lock:
            self.pixmap = QPixmap.fromImage(image)
            self.frame_width = image.width()
            self.frame_height = image.height()
            self.update()  # Request a redraw
    
    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key_Left:
            self.pan_angle = (self.pan_angle - self.pan_speed) % 360
            self.update()
        elif event.key() == Qt.Key_Right:
            self.pan_angle = (self.pan_angle + self.pan_speed) % 360
            self.update()
        elif event.key() == Qt.Key_Up:
            self.tilt_angle = max(-85, self.tilt_angle - self.pan_speed)
            self.update()
        elif event.key() == Qt.Key_Down:
            self.tilt_angle = min(85, self.tilt_angle + self.pan_speed)
            self.update()
        elif event.key() == Qt.Key_Plus or event.key() == Qt.Key_Equal:
            self.zoom_level = min(5.0, self.zoom_level + self.zoom_step)
            self.update()
        elif event.key() == Qt.Key_Minus:
            self.zoom_level = max(0.5, self.zoom_level - self.zoom_step)
            self.update()
        else:
            super().keyPressEvent(event)
    
    def mousePressEvent(self, event):
        """Start dragging with the mouse"""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
    
    def mouseReleaseEvent(self, event):
        """Stop dragging with the mouse"""
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.ArrowCursor)
    
    def mouseMoveEvent(self, event):
        """Handle mouse dragging for navigation"""
        if self.dragging and self.last_pos:
            # Calculate how far the mouse moved
            delta = event.pos() - self.last_pos
            
            # Update pan angle (horizontal movement)
            # Map x movement to angle change (360 degrees maps to full frame width)
            angle_per_pixel = 360.0 / self.width()
            self.pan_angle = (self.pan_angle - delta.x() * angle_per_pixel) % 360
            
            # Update tilt angle (vertical movement)
            # Map y movement to angle change (170 degrees maps to full frame height)
            angle_per_pixel_y = 170.0 / self.height()
            self.tilt_angle = max(-85, min(85, self.tilt_angle + delta.y() * angle_per_pixel_y))
            
            self.last_pos = event.pos()
            self.update()
    
    def wheelEvent(self, event):
        """Handle mouse wheel for zooming"""
        delta = event.angleDelta().y()
        if delta > 0:
            # Zoom in
            self.zoom_level = min(5.0, self.zoom_level + self.zoom_step)
        else:
            # Zoom out
            self.zoom_level = max(0.5, self.zoom_level - self.zoom_step)
        self.update()
    
    def _draw_overlay(self, painter):
        """Draw informational overlay with compass, etc."""
        try:
            # Draw semi-transparent info panel
            from PyQt5.QtGui import QColor  # Import inside function as fallback
            
            # Draw semi-transparent info panel (using Qt.black with alpha instead of QColor)
            painter.fillRect(10, 10, 250, 30, QColor(0, 0, 0, 128))
            painter.setPen(Qt.white)
            painter.drawText(
                15, 30, 
                f"Pan: {self.pan_angle:.1f}° | Tilt: {self.tilt_angle:.1f}° | Zoom: {self.zoom_level:.1f}x"
            )
            
            # Draw compass at the bottom
            compass_width = 200
            compass_height = 30
            compass_x = (self.width() - compass_width) // 2
            compass_y = self.height() - compass_height - 10
            
            # Background (using Qt.black with alpha instead of QColor)
            painter.fillRect(compass_x, compass_y, compass_width, compass_height, QColor(0, 0, 0, 128))
            
            # Draw cardinal directions
            painter.setPen(Qt.white)
            directions = ["N", "E", "S", "W"]
            for i, direction in enumerate(directions):
                angle = i * 90
                # Calculate position based on current pan
                relative_angle = (angle - self.pan_angle) % 360
                x_pos = compass_x + int((relative_angle / 360) * compass_width)
                
                # Only draw if it's within the compass area
                if compass_x <= x_pos < compass_x + compass_width:
                    painter.drawText(x_pos, compass_y + 20, direction)
            
            # Draw current view indicator
            indicator_pos = compass_x + compass_width // 2
            painter.setPen(QPen(Qt.red, 2))
            painter.drawLine(indicator_pos, compass_y, indicator_pos, compass_y + compass_height)
        
        except Exception as e:
            print(f"Error in _draw_overlay: {e}")
            # Fallback to a simpler overlay without using QColor
            try:
                painter.setPen(Qt.white)
                painter.drawText(
                    15, 30, 
                    f"Pan: {self.pan_angle:.1f}° | Tilt: {self.tilt_angle:.1f}° | Zoom: {self.zoom_level:.1f}x"
                )
            except Exception as e2:
                print(f"Failed even with simple overlay: {e2}")

    def paintEvent(self, event):
        """Draw the 360° view"""
        if not self.pixmap or self.pixmap.isNull():
            # No frame yet, just draw a placeholder
            painter = QPainter(self)
            try:
                painter.fillRect(self.rect(), Qt.black)
                painter.setPen(Qt.white)
                painter.drawText(self.rect(), Qt.AlignCenter, "Waiting for 360° video...")
            finally:
                painter.end()
            return
            
        painter = QPainter(self)
        
        try:
            # Calculate the source region to display (based on pan/tilt/zoom)
            # For equirectangular projection:
            
            # Calculate the viewport center based on pan/tilt
            # For pan: 0° -> 0, 360° -> frame_width
            pan_pixel = int((self.pan_angle / 360.0) * self.frame_width)
            
            # For tilt: -90° -> 0, 90° -> frame_height
            tilt_pixel = int(((self.tilt_angle + 90) / 180.0) * self.frame_height)
            
            # Calculate view region based on zoom
            view_width = int(self.width() / self.zoom_level)
            view_height = int(self.height() / self.zoom_level)
            
            # Calculate source rectangle
            src_x = pan_pixel - view_width // 2
            src_y = tilt_pixel - view_height // 2
            
            # Handle horizontal wrapping (important for 360° view)
            if src_x < 0:
                # Draw the part from the right side of the image
                right_width = min(-src_x, view_width)
                if right_width > 0:
                    # Create source and target rectangles
                    source_rect = QRect(self.frame_width + src_x, src_y, right_width, view_height)
                    target_rect = QRect(0, 0, right_width, self.height())
                    painter.drawPixmap(target_rect, self.pixmap, source_rect)
                
                # Draw the main part from the left side
                source_rect = QRect(0, src_y, view_width - right_width, view_height)
                target_rect = QRect(right_width, 0, self.width() - right_width, self.height())
                painter.drawPixmap(target_rect, self.pixmap, source_rect)
                
            elif src_x + view_width > self.frame_width:
                # Draw the main part
                left_width = self.frame_width - src_x
                
                # Calculate what portion of the target width this represents
                target_left_width = int(left_width * (self.width() / view_width))
                
                # Create source and target rectangles
                source_rect = QRect(src_x, src_y, left_width, view_height)
                target_rect = QRect(0, 0, target_left_width, self.height())
                painter.drawPixmap(target_rect, self.pixmap, source_rect)
                
                # Draw the wrapped part from the beginning of the image
                source_rect = QRect(0, src_y, view_width - left_width, view_height)
                target_rect = QRect(target_left_width, 0, self.width() - target_left_width, self.height())
                painter.drawPixmap(target_rect, self.pixmap, source_rect)
                
            else:
                # No wrapping needed - draw the entire view
                # Create source and target rectangles
                source_rect = QRect(src_x, src_y, view_width, view_height)
                target_rect = QRect(0, 0, self.width(), self.height())
                painter.drawPixmap(target_rect, self.pixmap, source_rect)
            
            # Draw compass indicator and overlay info
            self._draw_overlay(painter)
            
        except Exception as e:
            import traceback
            print(f"Error in paintEvent: {e}")
            traceback.print_exc()
            
        finally:
            # Always make sure to end the painter
            painter.end()

class Interactive360CameraWindow(QMainWindow):
    """Interactive 360° camera viewer window that uses the existing feed"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interactive 360° Camera")
        self.resize(800, 450)  # 16:9 aspect ratio
        
        # Create main widget and layout
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        
        # Create the interactive view
        self.view = Interactive360View()
        layout.addWidget(self.view)
        
        # Add control sliders for mouse-free operation
        controls_layout = QHBoxLayout()
        
        # Pan slider (horizontal rotation)
        self.pan_slider = QSlider(Qt.Horizontal)
        self.pan_slider.setRange(0, 360)
        self.pan_slider.setValue(0)
        self.pan_slider.setTracking(True)
        self.pan_slider.valueChanged.connect(self.update_pan)
        
        # Tilt slider (vertical rotation)
        self.tilt_slider = QSlider(Qt.Horizontal)
        self.tilt_slider.setRange(-85, 85)
        self.tilt_slider.setValue(0)
        self.tilt_slider.setTracking(True)
        self.tilt_slider.valueChanged.connect(self.update_tilt)
        
        # Zoom slider
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(5, 50)  # 0.5x to 5.0x zoom
        self.zoom_slider.setValue(10)  # 1.0x zoom
        self.zoom_slider.setTracking(True)
        self.zoom_slider.valueChanged.connect(self.update_zoom)
        
        # Add sliders to control layout
        controls_layout.addWidget(QLabel("Pan:"))
        controls_layout.addWidget(self.pan_slider)
        controls_layout.addWidget(QLabel("Tilt:"))
        controls_layout.addWidget(self.tilt_slider)
        controls_layout.addWidget(QLabel("Zoom:"))
        controls_layout.addWidget(self.zoom_slider)
        
        layout.addLayout(controls_layout)
        
        # Add instructions
        instructions = QLabel(
            "Use arrow keys or sliders to navigate. "
            "Mouse drag to pan/tilt, scroll wheel to zoom."
        )
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setStyleSheet("background-color: rgba(0,0,0,128); color: white; padding: 4px;")
        layout.addWidget(instructions)
        
        self.setCentralWidget(main_widget)
        
        # Start the frame grabber
        self.start_frame_grabber()
    
    def update_pan(self, value):
        """Update pan angle from slider"""
        self.view.pan_angle = value
        self.view.update()
    
    def update_tilt(self, value):
        """Update tilt angle from slider"""
        self.view.tilt_angle = value
        self.view.update()
    
    def update_zoom(self, value):
        """Update zoom level from slider"""
        self.view.zoom_level = value / 10.0
        self.view.update()
    
    def start_frame_grabber(self):
        """Start the frame grabber to monitor the 360 camera feed"""
        # Get the port from configuration
        config = CameraConfig()
        self.port = config.config.get("camera_360_port", 5001)
        
        # Initialize GStreamer if needed
        if not hasattr(Gst, 'is_initialized') or not Gst.is_initialized():
            Gst.init(None)
        
        # Create a pipeline that receives the stream but doesn't display it
        # This will work alongside the existing viewer
        pipeline_str = (
            f'udpsrc port={self.port} '
            'caps="application/x-rtp,media=video,encoding-name=H264,payload=96" ! '
            'rtpjitterbuffer latency=0 drop-on-latency=true ! rtph264depay ! '
            'h264parse ! decodebin ! videoconvert ! '
            'video/x-raw,format=RGB ! '
            'appsink name=appsink emit-signals=true sync=false'
        )
        
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
            
            # Get the appsink element for frame access
            self.appsink = self.pipeline.get_by_name('appsink')
            self.appsink.connect('new-sample', self.on_new_sample)
            
            # Setup bus for messages
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect('message', self.on_message)
            
            # Start playing
            self.pipeline.set_state(Gst.State.PLAYING)
            
            print(f"Started frame grabber for 360 camera on port {self.port}")
            
        except Exception as e:
            print(f"Error starting frame grabber: {e}")
            import traceback
            traceback.print_exc()
    
    def on_new_sample(self, appsink):
        """Process new video frames from the appsink"""
        try:
            # Get the sample
            sample = appsink.emit('pull-sample')
            if not sample:
                return Gst.FlowReturn.OK
                
            # Get the buffer and caps
            buffer = sample.get_buffer()
            caps = sample.get_caps()
            structure = caps.get_structure(0)
            width = structure.get_value('width') 
            height = structure.get_value('height')
            
            # Map the buffer to get access to the data
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if success:
                # Get the frame data as numpy array
                frame_data = np.ndarray(
                    shape=(height, width, 3),
                    dtype=np.uint8,
                    buffer=map_info.data
                )
                
                # Convert to QImage (RGB format)
                image = QImage(
                    frame_data.data,
                    width,
                    height,
                    frame_data.strides[0],
                    QImage.Format_RGB888
                )
                
                # Send to the view widget
                self.view.set_frame(image)
                
                # Clean up
                buffer.unmap(map_info)
            
            return Gst.FlowReturn.OK
            
        except Exception as e:
            print(f"Error processing video sample: {e}")
            return Gst.FlowReturn.ERROR
    
    def on_message(self, bus, message):
        """Handle GStreamer messages"""
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"GStreamer Error: {err}: {debug}")
        elif t == Gst.MessageType.EOS:
            print("End of stream")
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending_state = message.parse_state_changed()
                print(f"Pipeline state changed from {old_state.value_nick} to {new_state.value_nick}")
    
    def closeEvent(self, event):
        """Clean up GStreamer pipeline when closing"""
        if hasattr(self, 'pipeline'):
            self.pipeline.set_state(Gst.State.NULL)
        super().closeEvent(event)