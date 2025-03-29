import cv2
import numpy as np

# Load the frame
img = cv2.imread("WIN_20250328_16_12_11_Pro.png")

# Split into two fisheye images (left and right)
h, w = img.shape[:2]
left = img[:, :w//2]
right = img[:, w//2:]

# Output dimensions (equirectangular)
out_w = 2 * 1024  # you can adjust this
out_h = 1024

# Empty output panorama
output = np.zeros((out_h, out_w, 3), dtype=np.uint8)

# Projection function
def fisheye_to_equirectangular(fisheye_img, center_shift=0):
    height, width = fisheye_img.shape[:2]
    fov = 180  # approximate field of view of each lens
    radius = width / 2

    equi_img = np.zeros((out_h, out_w // 2, 3), dtype=np.uint8)

    for y in range(out_h):
        for x in range(out_w // 2):
            theta = (x / (out_w // 2)) * 2 * np.pi - np.pi  # [-pi, pi]
            phi = (y / out_h) * np.pi  # [0, pi]

            # Convert spherical to fisheye plane
            X = np.sin(phi) * np.sin(theta)
            Y = np.cos(phi)
            Z = np.sin(phi) * np.cos(theta)

            r = radius * np.arccos(Z) / (0.5 * np.pi)  # equidistant projection
            fx = int(width/2 + r * X)
            fy = int(height/2 + r * Y)

            if 0 <= fx < width and 0 <= fy < height:
                equi_img[y, x] = fisheye_img[fy, fx]

    return equi_img

# Convert each half
equi_left = fisheye_to_equirectangular(left)
equi_right = fisheye_to_equirectangular(right)

# Stitch side by side
output[:, :out_w // 2] = equi_left
output[:, out_w // 2:] = equi_right

# Show & Save
cv2.imshow("Equirectangular Panorama", output)
cv2.imwrite("stitched_photosphere.jpg", output)
cv2.waitKey(0)
cv2.destroyAllWindows()
