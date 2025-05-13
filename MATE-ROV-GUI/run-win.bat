@echo off
REM Set path to MSYS2 installation
set MSYS2_PATH=C:\msys64
set PATH=%MSYS2_PATH%\mingw64\bin;%MSYS2_PATH%\usr\bin;%PATH%

REM Set GStreamer environment variables for MSYS2
set GST_PLUGIN_PATH=%MSYS2_PATH%\mingw64\lib\gstreamer-1.0
set GI_TYPELIB_PATH=%MSYS2_PATH%\mingw64\lib\girepository-1.0

REM Run the app with MSYS2 Python
%MSYS2_PATH%\mingw64\bin\python.exe "%~dp0%~nx1"