

# Import all neccessary Libraries
import cv2
import numpy as np
import pandas as pd
import matplotlib

def nothing(x):
    pass

# Load an image
image_path = "BaseMarked.png"  # Replace with the path to your image
image = cv2.imread(image_path)
if image is None:
    print("Error: Unable to load image. Please check the path.")
    exit()

# Convert the image to HSV color space
hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

# Create a window
cv2.namedWindow("HSV Thresholding")

# Create trackbars for upper and lower HSV values
cv2.createTrackbar("Lower H", "HSV Thresholding", 0, 179, nothing)
cv2.createTrackbar("Lower S", "HSV Thresholding", 0, 255, nothing)
cv2.createTrackbar("Lower V", "HSV Thresholding", 0, 255, nothing)

cv2.createTrackbar("Upper H", "HSV Thresholding", 179, 179, nothing)
cv2.createTrackbar("Upper S", "HSV Thresholding", 255, 255, nothing)
cv2.createTrackbar("Upper V", "HSV Thresholding", 255, 255, nothing)

while True:
    # Get current positions of trackbars
    lower_h = cv2.getTrackbarPos("Lower H", "HSV Thresholding")
    lower_s = cv2.getTrackbarPos("Lower S", "HSV Thresholding")
    lower_v = cv2.getTrackbarPos("Lower V", "HSV Thresholding")

    upper_h = cv2.getTrackbarPos("Upper H", "HSV Thresholding")
    upper_s = cv2.getTrackbarPos("Upper S", "HSV Thresholding")
    upper_v = cv2.getTrackbarPos("Upper V", "HSV Thresholding")

    # Define HSV thresholds
    lower_bound = np.array([lower_h, lower_s, lower_v])
    upper_bound = np.array([upper_h, upper_s, upper_v])

    # Apply the threshold
    mask = cv2.inRange(hsv_image, lower_bound, upper_bound)

    # Apply the mask to the original image
    result = cv2.bitwise_and(image, image, mask=mask)

    # Show the original, mask, and result
    cv2.imshow("Original Image", image)
    cv2.imshow("Mask", mask)
    cv2.imshow("Result", result)

    # Break the loop if 'q' is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release resources
cv2.destroyAllWindows()