import sys
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstVideo
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtGui import QImage, QPixmap
from gi.repository import Gst # Ensure Gst is imported
import os

class VideoWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        # must have a native window handle for GstVideoOverlay
        self.setAttribute(QtCore.Qt.WA_NativeWindow)
        self.setMinimumSize(320, 240)  # Smaller size for grid layout

class CameraStream(QtWidgets.QWidget):
    def __init__(self, pipeline_desc, label_text="Camera Feed"):
        super().__init__()
        self.video_widget = VideoWidget()
        layout = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel(label_text)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet("font-weight: bold; background-color: #333; color: white; padding: 2px;")
        layout.addWidget(self.label)
        layout.addWidget(self.video_widget)
        layout.setStretch(1, 1)

        self.camera_name = label_text # Store camera name for debugging
        self._latest_captured_pixmap = QPixmap() # For storing the frame from appsink
        self._appsink_connection_id = None # To store appsink signal connection ID

        try:
            if not hasattr(Gst, 'is_initialized') or not Gst.is_initialized():
                Gst.init(None)
            
            available_sinks = []
            for sink_name_option in ['d3dvideosink', 'glimagesink', 'ximagesink', 'autovideosink']: # Added autovideosink as a fallback
                element = Gst.ElementFactory.make(sink_name_option, None)
                if element:
                    available_sinks.append(sink_name_option)
                    element = None # Dereference
            
            if not available_sinks:
                raise Exception("No suitable video sink found for embedding")
            
            chosen_display_sink_factory_name = available_sinks[0]
            print(f"Using {chosen_display_sink_factory_name} for embedding in {self.camera_name}")
            
            modified_pipeline = pipeline_desc
            # This replacement logic is for the *display* branch of the tee.
            # The 'autovideosink' in the camera_config.py for the display branch will be targeted here.
            if 'autovideosink' in modified_pipeline:
                 modified_pipeline = modified_pipeline.replace(
                    'autovideosink sync=false', 
                    f'{chosen_display_sink_factory_name} name=sink sync=false', 
                    1 # Replace only the first occurrence (for the display branch)
                )
            elif 'fpsdisplaysink' in modified_pipeline: # Fallback if fpsdisplaysink was used
                 modified_pipeline = modified_pipeline.replace(
                    'fpsdisplaysink sync=false',
                    f'{chosen_display_sink_factory_name} name=sink sync=false',
                    1
                )
            else:
                # If neither autovideosink nor fpsdisplaysink is explicitly in the display branch
                # (e.g., if the pipeline was already specific), we assume 'name=sink' is the target.
                # This part might need adjustment if your non-360 pipelines are very different.
                print(f"Warning: 'autovideosink' or 'fpsdisplaysink' not found for explicit replacement in {self.camera_name}. Assuming 'name=sink' is correctly configured if present.")


            print(f"Creating pipeline for {self.camera_name}: {modified_pipeline}")
            self.pipeline = Gst.parse_launch(modified_pipeline)
            
            display_sink = self.pipeline.get_by_name("sink") # This is the d3dvideosink/glimagesink etc.
            if not display_sink:
                # If the pipeline for camera_360 was correctly modified in camera_config.py,
                # 'autovideosink' in its display branch should have been replaced by, e.g., 'd3dvideosink name=sink'.
                print(f"ERROR: Could not find display sink element 'sink' in pipeline for {self.camera_name}")
                # Fallback: try to find any of the known sink types if 'name=sink' wasn't set as expected
                for sn in available_sinks:
                    element = self.pipeline.get_by_name(sn) # Try getting by factory name if 'name=sink' failed
                    if element:
                        display_sink = element
                        print(f"INFO: Found display sink by factory name '{sn}' for {self.camera_name}")
                        break
                if not display_sink:
                     raise Exception(f"Could not find display sink element in pipeline for {self.camera_name}")

            display_sink.set_window_handle(int(self.video_widget.winId()))
            
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect('message', self.on_message)

            # ---- APPSINK SETUP ----
            appsink_element = self.pipeline.get_by_name("photosphere_appsink")
            if appsink_element:
                print(f"DEBUG: Found 'photosphere_appsink' for {self.camera_name}")
                self._appsink_connection_id = appsink_element.connect("new-sample", self._on_new_sample_from_appsink)
            else:
                # This is not an error for non-360 cameras, as they won't have this appsink.
                if "360 Camera" in self.camera_name: # Only print error if it's the 360 camera
                    print(f"ERROR: 'photosphere_appsink' not found in pipeline for {self.camera_name}. Frame capture will not work.")
            # ---- END APPSINK SETUP ----
            
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                print(f"Failed to start pipeline for {self.camera_name}")
                raise Exception("Failed to start pipeline")
                
            print(f"Pipeline started for {self.camera_name}")
            
        except Exception as e:
            print(f"Error creating GStreamer pipeline for {self.camera_name}: {e}")
            import traceback
            traceback.print_exc()
            error_label = QtWidgets.QLabel(f"Camera Error ({self.camera_name}): {str(e)}")
            error_label.setStyleSheet("color: red; background-color: #ffeeee; padding: 10px;")
            error_label.setAlignment(QtCore.Qt.AlignCenter)
            error_label.setWordWrap(True)
            # Check if layout is already set, otherwise it might crash here
            if self.layout() is None:
                fallback_layout = QtWidgets.QVBoxLayout(self)
                fallback_layout.addWidget(error_label)
            else:
                self.layout().addWidget(error_label)

    def _on_new_sample_from_appsink(self, appsink):
        sample = appsink.emit("pull-sample")
        if not sample:
            return Gst.FlowReturn.OK

        buffer = sample.get_buffer()
        caps = sample.get_caps()
        structure = caps.get_structure(0)
        width = structure.get_value("width")
        height = structure.get_value("height")
        # format_name = structure.get_value("format") # Expected RGB

        success, map_info = buffer.map(Gst.MapFlags.READ)
        if success:
            # .copy() is important here!
            image = QImage(map_info.data, width, height, QImage.Format_RGB888).copy()
            self._latest_captured_pixmap = QPixmap.fromImage(image)
            buffer.unmap(map_info)
        else:
            print(f"ERROR: Failed to map buffer for appsink in {self.camera_name}")
        
        return Gst.FlowReturn.OK

    def get_latest_frame_for_photosphere(self):
        if self._latest_captured_pixmap.isNull():
            print(f"DEBUG ({self.camera_name}): get_latest_frame_for_photosphere called, but pixmap is null.")
        else:
            print(f"DEBUG ({self.camera_name}): get_latest_frame_for_photosphere returning valid pixmap.")
        return self._latest_captured_pixmap
    
    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"GStreamer Error: {err}: {debug}")
            self.label.setText(f"{self.label.text()} - Error")
            self.label.setStyleSheet("font-weight: bold; background-color: #a00; color: white; padding: 2px;")
            
        elif t == Gst.MessageType.EOS:
            print("End of stream")
            
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending_state = message.parse_state_changed()
                print(f"Pipeline state changed from {old_state.value_nick} to {new_state.value_nick}")

    def close(self):
        try:
            # ---- APPSINK CLEANUP ----
            if self.pipeline and self._appsink_connection_id is not None:
                appsink_element = self.pipeline.get_by_name("photosphere_appsink")
                if appsink_element and appsink_element.handler_is_connected(self._appsink_connection_id):
                    appsink_element.disconnect(self._appsink_connection_id)
                    self._appsink_connection_id = None
                    print(f"DEBUG: Disconnected new-sample signal from photosphere_appsink for {self.camera_name}")
            # ---- END APPSINK CLEANUP ----
            if hasattr(self, 'pipeline') and self.pipeline is not None:
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline = None # Dereference
        except Exception as e:
            print(f"Error closing pipeline for {self.camera_name}: {e}")
        # super().close() # QWidget doesn't have a close that takes arguments like QMainWindow
        # If CameraStream is a QWidget, its cleanup is handled by Python's garbage collection
        # or when its parent is destroyed. If you need specific QWidget cleanup, do it here.


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        print("DEBUG - CameraWindow.__init__: Starting camera initialization")
        try:
            print("DEBUG - CameraWindow: Creating grid layout")
            main_widget = QtWidgets.QWidget()
            # Use a grid layout with 2 columns initially, can expand later
            grid_layout = QtWidgets.QGridLayout(main_widget)
            grid_layout.setSpacing(10)  # Add some spacing between cameras
            self.setCentralWidget(main_widget)

            print("DEBUG - CameraWindow: Checking GStreamer environment")
            print(f"GST_PLUGIN_PATH: {os.environ.get('GST_PLUGIN_PATH', 'Not set')}")
            print(f"GI_TYPELIB_PATH: {os.environ.get('GI_TYPELIB_PATH', 'Not set')}")
            
            # Initialize a list to store all camera widgets for cleanup
            self.camera_widgets = []
            
            # 1. USB Camera (JPEG stream on port 5004)
            usb_pipeline = (
                'udpsrc port=5004 caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" ! '
                'rtpjitterbuffer latency=0 drop-on-latency=true ! '
                'rtpjpegdepay ! jpegdec ! videoconvert ! videoflip method=counterclockwise ! '
                'autovideosink sync=false'
            )

            usb_pipeline2 = (
                'udpsrc port=5005 caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" ! '
                'rtpjitterbuffer latency=0 drop-on-latency=true ! '
                'rtpjpegdepay ! jpegdec ! videoconvert ! videoflip method=counterclockwise ! '
                'autovideosink sync=false'
            )
            usb_camera = CameraStream(usb_pipeline, "USB Camera")
            grid_layout.addWidget(usb_camera, 0, 0)
            self.camera_widgets.append(usb_camera)

            usb_camera2 = CameraStream(usb_pipeline2, "USB Camera 2")
            grid_layout.addWidget(usb_camera2, 0, 1)
            self.camera_widgets.append(usb_camera2)
            
            # 2. ZED Camera (H264 stream on port 5000)
            # zed_pipeline = (
            #     'udpsrc port=5000 caps="application/x-rtp, media=video, encoding-name=H264, payload=96" ! '
            #     'rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! '
            #     'fpsdisplaysink sync=false'
            # )
            # zed_camera = CameraStream(zed_pipeline, "ZED Camera")
            # grid_layout.addWidget(zed_camera, 0, 1)
            # self.camera_widgets.append(zed_camera)
            
            # Setup for additional cameras - just add new ones to the grid
            # Example of how to add more cameras in the future:
            # camera3 = CameraStream(...pipeline..., "Camera 3")
            # grid_layout.addWidget(camera3, 1, 0)  # row 1, col 0
            # self.camera_widgets.append(camera3)
            
            # camera4 = CameraStream(...pipeline..., "Camera 4")
            # grid_layout.addWidget(camera4, 1, 1)  # row 1, col 1
            # self.camera_widgets.append(camera4)
            
            print("DEBUG - CameraWindow successfully initialized")
            
        except Exception as e:
            print(f"DEBUG - Error creating camera window: {e}")
            import traceback
            traceback.print_exc()
            
            # Show error in UI
            error_widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(error_widget)
            error_label = QtWidgets.QLabel(f"Failed to initialize cameras: {str(e)}")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: red; font-size: 14px; background-color: #ffeeee; padding: 10px;")
            layout.addWidget(error_label)
            self.setCentralWidget(error_widget)
    
    def closeEvent(self, event):
        # Clean up pipelines
        try:
            for camera in self.camera_widgets:
                camera.close()
        except Exception as e:
            print(f"Error closing pipelines: {e}")
        super().closeEvent(event)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.resize(800, 600)
    win.show()
    sys.exit(app.exec_())