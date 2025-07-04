@echo off
    setlocal
    REM This script changes its directory to where it is located.
    cd /D "%~dp0"
    echo Current directory for ffmpeg: %cd%
    echo Running FFmpeg command:
    echo ffmpeg -i input.jpg -vf "v360=input=dfisheye:ih_fov=195:iv_fov=195:output=equirect:out_stereo=none" -q:v 1 output.jpg -y

    ffmpeg -i input.jpg -vf "v360=input=dfisheye:ih_fov=195:iv_fov=195:output=equirect:out_stereo=none" -q:v 1 output.jpg -y

    if %errorlevel% neq 0 (
        echo FFmpeg command failed. Errorlevel: %errorlevel%
        exit /b 1
    )
    echo FFmpeg command successful.
    exit /b 0
    endlocal
    