import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys
import os

# This script will run its own GStreamer pipeline to display the video.
# Ensure GStreamer (including plugins like d3dvideosink or autovideosink)
# is correctly installed and in your PATH or set GST_PLUGIN_PATH if needed.
# e.g., os.environ["GST_PLUGIN_PATH"] = "C:\\gstreamer\\1.0\\msvc_x86_64\\lib\\gstreamer-1.0"

def on_bus_message(bus, message, loop):
    mtype = message.type
    if mtype == Gst.MessageType.EOS:
        print("HDMI Output: End-of-stream received.")
        loop.quit()
    elif mtype == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f"HDMI Output Error: {message.src.get_name()} - {err.message}")
        if debug:
            print(f"Debugging info: {debug}")
        loop.quit()
    return True

def main():
    Gst.init(None)

    # This pipeline listens to the UDP port (5008) where the main GUI's
    # "USB Camera 2" pipeline is teeing its output.
    # The feed arriving here is already rotated counter-clockwise by camera_config.py.
    # We apply a rotate-180 to achieve a net 90-degree clockwise rotation from original.
    pipeline_str = (
        'udpsrc port=5008 caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" ! '
        'rtpjitterbuffer latency=0 drop-on-latency=true ! '
        'rtpjpegdepay ! jpegdec ! videoconvert ! ' 
        'autovideosink sync=false'
    )

    print(f"Launching HDMI output pipeline for USB Camera 2: {pipeline_str}")
    pipeline = Gst.parse_launch(pipeline_str)

    if not pipeline:
        print("ERROR: Could not create HDMI output pipeline for USB Camera 2.")
        sys.exit(1)

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    loop = GLib.MainLoop()
    bus.connect("message", on_bus_message, loop)

    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("ERROR: Unable to set the HDMI pipeline to the playing state.")
        pipeline.set_state(Gst.State.NULL) # Clean up
        sys.exit(1)

    print("HDMI output script for USB Camera 2 is running.")
    print("A new window should appear with the USB Camera 2 feed, rotated 90 degrees clockwise from original.")
    print("Manually DRAG this window to your HDMI-connected second monitor and make it FULLSCREEN (usually F11).")

    try:
        loop.run()
    except KeyboardInterrupt:
        print("Ctrl+C pressed, shutting down HDMI output script.")
    finally:
        print("Setting HDMI pipeline to NULL state.")
        pipeline.set_state(Gst.State.NULL)
        bus.remove_signal_watch()

if __name__ == '__main__':
    main()