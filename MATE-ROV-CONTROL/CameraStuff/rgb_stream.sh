#!/bin/bash

gst-launch-1.0 zedsrc camera-resolution=3 camera-fps=30 stream-type=0 ! \
videoconvert ! x264enc byte-stream=true tune=zerolatency speed-preset=superfast bitrate=10000 ! \
h264parse ! rtph264pay config-interval=-1 pt=96 ! \
udpsink host=192.168.1.97 port=5000 sync=false async=false
