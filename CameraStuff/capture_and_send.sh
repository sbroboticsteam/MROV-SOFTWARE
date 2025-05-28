#!/bin/bash
echo "Stopping RGB stream..."
pkill -f gst-launch-1.0

echo "Capturing depth map..."
python3 capture_depth.py

echo "Transferring file to host..."
scp Pointcloud.ply giova@192.168.1.97:Pointcloud/

echo "Restarting RGB stream..."
./rgb_stream.sh
