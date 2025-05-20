gst-launch-1.0 -v udpsrc port=5004 caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" ! rtpjitterbuffer latency=0 drop-on-latency=true ! rtpjpegdepay ! jpegdec ! videoconvert ! autovideosink sync=false

