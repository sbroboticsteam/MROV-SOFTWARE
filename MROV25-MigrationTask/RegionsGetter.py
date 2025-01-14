# Import all neccessary Libraries
import cv2
import numpy as np
import pandas as pd
import matplotlib

# Read the image
marked = cv2.imread('BaseMarked.png')

# Convert the image to HSV colorspace
marked = cv2.cvtColor(marked, cv2.COLOR_BGR2HSV)

# Filter Regions based on HSV values

# Region 1
lower = np.array([179,196,194])
upper = np.array([179,255,255])
mask_reg1 = cv2.inRange(marked, lower, upper)

# Region 2
lower = np.array([46, 130, 56])
upper = np.array([58, 255, 255])
mask_reg2 = cv2.inRange(marked, lower, upper)

# Region 3
lower = np.array([2, 168, 184])
upper = np.array([12, 255, 255])
mask_reg3 = cv2.inRange(marked, lower, upper)

# Region 4
lower = np.array([111, 75, 49])
upper = np.array([127, 255, 255])
mask_reg4 = cv2.inRange(marked, lower, upper)

# Region 5
lower = np.array([37, 168, 125])
upper = np.array([104, 187, 141])
mask_reg5 = cv2.inRange(marked, lower, upper)

## Note: DO NOT CHANGE the hsv values for the regions. They are the correct values for the regions in the image.

# Function to combine the masks based on migration data
def combine_masks(image, data, masks=[mask_reg1, mask_reg2, mask_reg3, mask_reg4, mask_reg5]):
    # Make Blank Mask
    combined_mask = np.zeros((image.shape[0], image.shape[1]), dtype=np.uint8)
    # Iterate through the data and Combine the masks based on the data of Migration
    for i in range(len(data)):
        if data[i] == 'Y':
            combined_mask = cv2.bitwise_or(combined_mask, masks[i])
    # Return the combined mask
    return combined_mask
        
# Function to display the regions on an unmarked image
def display_regions(mask, imagepath = 'BaseUnmarked.png'):
    # Read in the unmarked image
    unmarked = cv2.imread(imagepath)
    color = (0,0,255) # Choose color red for migrations

    # Create a colored overlay with the same shape as the image
    colored_overlay = np.zeros_like(unmarked, dtype=np.uint8)
    colored_overlay[:] = color

    # Apply the mask to the colored overlay
    colored_part = cv2.bitwise_and(colored_overlay, colored_overlay, mask=mask)

    # Apply the inverse mask to the original image
    inverse_mask = cv2.bitwise_not(mask)
    background = cv2.bitwise_and(unmarked, unmarked, mask=inverse_mask)

    # Combine the colored part and the background
    result = cv2.add(background, colored_part)

    return result

# Function to put the year in the image
def put_year(image, number=6969):

    # Define text properties
    position = (10, 30)  # Top-left corner (x, y)
    font = cv2.FONT_HERSHEY_SIMPLEX  # Font type
    font_scale = 1  # Font size
    color = (255, 0, 0)  # White color in BGR
    thickness = 3  # Thickness of the text

    # Add the number to the image
    cv2.putText(image, str(number), position, font, font_scale, color, thickness)

    return image

if __name__ == '__main__':
    # Read the migration data
    df = pd.read_csv('SampleData.csv')

    # Iterate through each row
    for index, row in df.iterrows():
        data = [row['Region 1'], row['Region 2'], row['Region 3'], row['Region 4'], row['Region 5']]
        combined_mask = combine_masks(image=marked, data=data, masks=[mask_reg1, mask_reg2, mask_reg3, mask_reg4, mask_reg5])
        result = display_regions(combined_mask)
        result = put_year(result, number=row['Year'])
        cv2.imshow('Migration Visualization', result)
        cv2.waitKey(1000)