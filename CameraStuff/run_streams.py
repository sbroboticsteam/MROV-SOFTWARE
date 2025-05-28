import subprocess
import signal
import sys
import time

# 🔧 Configurable section
zed_ip = "192.168.1.142"
usb_ip = "192.168.1.142"

# Optional: customize ports if needed
zed_port = 5000
usb0_port = 5004
usb2_port = 5005

# Define GStreamer commands
commands = [
    [
        "gst-launch-1.0", "zedsrc", "camera-resolution=3", "camera-fps=30", "stream-type=0", "!",
        "videoconvert", "!", "x264enc", "byte-stream=true", "tune=zerolatency",
        "speed-preset=superfast", "bitrate=10000", "!", "h264parse", "!", "rtph264pay",
        "config-interval=-1", "pt=96", "!", "udpsink",
        f"host={zed_ip}", f"port={zed_port}", "sync=false", "async=false"
    ],
    [
        "gst-launch-1.0", "-v", "v4l2src", "device=/dev/video0", "!",
        "image/jpeg,width=640,height=480,framerate=30/1", "!", "jpegparse", "!",
        "rtpjpegpay", "pt=26", "!", "udpsink",
        f"host={usb_ip}", f"port={usb0_port}", "sync=false", "async=false"
    ],
    [
        "gst-launch-1.0", "-v", "v4l2src", "device=/dev/video2", "!",
        "image/jpeg,width=640,height=480,framerate=30/1", "!", "jpegparse", "!",
        "rtpjpegpay", "pt=26", "!", "udpsink",
        f"host={usb_ip}", f"port={usb2_port}", "sync=false", "async=false"
    ]
]

processes = []

def signal_handler(sig, frame):
    print("\n[INFO] Stopping all streams...")
    for p in processes:
        p.terminate()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    print("[INFO] Starting all streams...")
    try:
        for cmd in commands:
            print(f"[INFO] Launching: {' '.join(cmd)}")
            processes.append(subprocess.Popen(cmd))
        print("[INFO] Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)
