import sys
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstVideo
from PyQt5 import QtWidgets, QtCore

class VideoWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        # must have a native window handle for GstVideoOverlay
        self.setAttribute(QtCore.Qt.WA_NativeWindow)
        self.setMinimumSize(640, 480)

class StreamTab(QtWidgets.QWidget):
    def __init__(self, pipeline_desc, sink_name):
        super().__init__()
        self.video_widget = VideoWidget()
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.video_widget)

        # init GStreamer pipeline
        Gst.init(None)
        self.pipeline = Gst.parse_launch(pipeline_desc)
        sink = self.pipeline.get_by_name(sink_name)
        # On Windows, winId() is an HWND; cast to int
        sink.set_window_handle(int(self.video_widget.winId()))
        self.pipeline.set_state(Gst.State.PLAYING)

    def close(self):
        self.pipeline.set_state(Gst.State.NULL)
        super().close()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(tabs)

        # Jetson USB camera stream (receiving via UDP)
        # This is the same pipeline as in your usbcamera.bat but adapted for the Python API
        udp_stream_desc = (
            'udpsrc port=5004 caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" ! '
            'rtpjitterbuffer latency=0 drop-on-latency=true ! '
            'rtpjpegdepay ! jpegdec ! videoconvert ! '
            'd3dvideosink name=udp_sink sync=false'
        )
        tabs.addTab(StreamTab(udp_stream_desc, 'udp_sink'), "Jetson USB Camera")

    def closeEvent(self, event):
        # ensure all pipelines are torn down
        for i in range(self.centralWidget().count()):
            w = self.centralWidget().widget(i)
            w.close()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.resize(800, 600)
    win.show()
    sys.exit(app.exec_())