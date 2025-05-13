#!/bin/bash
# Make sure GST_PLUGIN_PATH is set correctly for MSYS2
export GST_PLUGIN_PATH=/mingw64/lib/gstreamer-1.0
# Run with Python
python "$@"