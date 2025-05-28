import cv2
# checking if your build of opencv supports gstreaner
print(cv2.getBuildInformation())

import platform

print(platform.python_compiler())