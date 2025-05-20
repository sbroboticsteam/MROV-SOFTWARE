@echo off
REM Full windows camera streaming commands

echo Starting CSI 0 Stream...
start "CSI 0" cmd /k gst-launch-1.0 -v udpsrc port=5000 caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=H264,payload=96" ! rtpjitterbuffer latency=0 drop-on-latency=true ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! autovideosink sync=false

echo Starting CSI 1 Stream...
start "CSI 1" cmd /k gst-launch-1.0 -v udpsrc port=5001 caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=H264,payload=96" ! rtpjitterbuffer latency=0 drop-on-latency=true ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! autovideosink sync=false

echo Starting Endoscope Stream...
start "Endoscope" cmd /k gst-launch-1.0 -v udpsrc port=5002 caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" ! rtpjitterbuffer latency=0 drop-on-latency=true ! rtpjpegdepay ! jpegdec ! videoconvert ! autovideosink sync=false

echo All streams launched.