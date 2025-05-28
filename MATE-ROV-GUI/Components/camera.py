import sys
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstVideo
from PyQt5 import QtWidgets, QtCore
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
        
        # Add label for camera identification
        self.label = QtWidgets.QLabel(label_text)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet("font-weight: bold; background-color: #333; color: white; padding: 2px;")
        layout.addWidget(self.label)
        
        # Add video widget where video will be embedded
        layout.addWidget(self.video_widget)
        layout.setStretch(1, 1)

        try:
            # Initialize GStreamer if needed
            if not hasattr(Gst, 'is_initialized') or not Gst.is_initialized():
                Gst.init(None)
            
            # Modify pipeline to use a sink that supports window handles
            # First find which sink is available
            available_sinks = []
            for sink_name in ['d3dvideosink', 'glimagesink', 'ximagesink']:
                element = Gst.ElementFactory.make(sink_name, None)
                if element:
                    available_sinks.append(sink_name)
                    element = None
            
            if not available_sinks:
                raise Exception("No suitable video sink found for embedding")
            
            # Use the first available sink
            sink_name = available_sinks[0]
            print(f"Using {sink_name} for embedding")
            
            # Replace autovideosink/fpsdisplaysink with the selected sink in the pipeline
            modified_pipeline = pipeline_desc
            for old_sink in ['autovideosink', 'fpsdisplaysink']:
                if old_sink in modified_pipeline:
                    modified_pipeline = modified_pipeline.replace(
                        f"{old_sink} sync=false", 
                        f"{sink_name} name=sink sync=false"
                    )
            
            print(f"Creating pipeline: {modified_pipeline}")
            self.pipeline = Gst.parse_launch(modified_pipeline)
            
            # Get the sink and set window handle
            sink = self.pipeline.get_by_name("sink")
            if not sink:
                raise Exception(f"Could not find sink element in pipeline")
            
            # Use GstVideoOverlay interface to embed video
            sink.set_window_handle(int(self.video_widget.winId()))
            
            # Setup bus for error messages
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect('message', self.on_message)
            
            # Start playing
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                print(f"Failed to start pipeline for {label_text}")
                raise Exception("Failed to start pipeline")
                
            print(f"Pipeline started for {label_text}")
            
        except Exception as e:
            print(f"Error creating GStreamer pipeline for {label_text}: {e}")
            import traceback
            traceback.print_exc()
            
            # Show error in UI
            error_label = QtWidgets.QLabel(f"Camera Error: {str(e)}")
            error_label.setStyleSheet("color: red; background-color: #ffeeee; padding: 10px;")
            error_label.setAlignment(QtCore.Qt.AlignCenter)
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
    
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
            if hasattr(self, 'pipeline'):
                self.pipeline.set_state(Gst.State.NULL)
        except Exception as e:
            print(f"Error closing pipeline: {e}")
        super().close()

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