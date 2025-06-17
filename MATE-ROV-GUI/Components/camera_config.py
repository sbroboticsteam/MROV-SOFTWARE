import os
import json
import socket
from PyQt5.QtCore import QObject, pyqtSignal

class CameraConfig(QObject):
    """Manages camera stream configurations for the application"""
    
    config_changed = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
        
        # Default configuration
        self.default_config = {
            "client_ip": self._get_local_ip(),
            "zed_port": 5000,
            "usb0_port": 5004,
            "usb2_port": 5005, 
            "camera_360_port": 5001  # Add 360 camera port
        }
        
        # Load saved configuration if available
        self.config = self.load_config()
    
    def _get_local_ip(self):
        """Get local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def load_config(self):
        """Load camera configuration from file"""
        config_file = os.path.join(self.config_dir, 'camera_config.json')
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                return config
            else:
                return self.default_config
        except:
            return self.default_config
    
    def save_config(self, config):
        """Save camera configuration to file"""
        config_file = os.path.join(self.config_dir, 'camera_config.json')
        
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            self.config = config
            self.config_changed.emit(config)
            return True
        except:
            return False
    
    def get_gstreamer_pipeline(self, camera_type):
        """Get GStreamer pipeline for the specified camera type"""
        if camera_type == "zed":
            return (
                f'udpsrc port={self.config["zed_port"]} caps="application/x-rtp, media=video, encoding-name=H264, payload=96" ! '
                'rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! '
                'autovideosink sync=false'
            )
        elif camera_type == "usb0":
            return (
                f'udpsrc port={self.config["usb0_port"]} caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" ! '
                'rtpjitterbuffer latency=0 drop-on-latency=true ! '
                'rtpjpegdepay ! jpegdec ! videoconvert ! videoflip method=counterclockwise ! '
                'autovideosink sync=false'
            )
        elif camera_type == "usb2":
            return (
                f'udpsrc port={self.config["usb2_port"]} caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" ! '
                'rtpjitterbuffer latency=0 drop-on-latency=true ! '
                'rtpjpegdepay ! jpegdec ! videoconvert ! videoflip method=counterclockwise ! '
                'tee name=usb2_hdmi_tee '
                # Branch 1: To the GUI (CameraStream will replace autovideosink with a named sink like d3dvideosink)
                'usb2_hdmi_tee. ! queue ! autovideosink sync=false '
                # Branch 2: To a new UDP port for an external HDMI display script
                # The external script will have a udpsrc on port 5008 (example)
                # We re-encode to JPEG and pay to RTP to send it over UDP again.
                'usb2_hdmi_tee. ! queue ! jpegenc ! rtpjpegpay ! udpsink host=127.0.0.1 port=5008 sync=false'
            )
        elif camera_type == "camera_360":
            return (
                f'udpsrc port={self.config["camera_360_port"]} caps="application/x-rtp,media=video,encoding-name=H264,payload=96" ! '
                'rtpjitterbuffer latency=0 drop-on-latency=true ! rtph264depay ! '
                'avdec_h264 ! videoconvert ! tee name=photosphere_tee ' # Tee after the main videoconvert
                # Branch 1: to the display sink (CameraStream will replace autovideosink with d3dvideosink name=sink)
                '! queue ! autovideosink sync=false ' 
                # Branch 2: to our appsink for frame capture
                'photosphere_tee. ! queue ! videoconvert ! video/x-raw,format=RGB ! appsink name=photosphere_appsink emit-signals=true max-buffers=1 drop=true sync=false'
            )
        else:
            raise ValueError(f"Unknown camera type: {camera_type}")