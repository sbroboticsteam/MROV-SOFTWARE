import cv2
import time
import screeninfo

def output_to_hdmi():
    rtsp_url='rtsp://admin:admin@192.168.1.198/media/video1?tcp'

    # Set up display for HDMI output
    target_display = None
    
    # Get information about connected displays
    monitors = screeninfo.get_monitors()
    
    if len(monitors) > 1:
        # Use the second monitor (typically the HDMI display)
        target_display = monitors[1]
        print(f"Using secondary display: {target_display.width}x{target_display.height} at ({target_display.x},{target_display.y})")
    else:
        print("Only one display detected, using primary display")
    
    # Open the webcam
    cap = cv2.VideoCapture(rtsp_url)
    
    if not cap.isOpened():
        print("Error: Could not open video source")
        return
    
    # Get video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Create window
    window_name = 'HDMI Output'
    cv2.namedWindow(window_name, cv2.WND_PROP_FULLSCREEN)
    
    # Position window on the target display if available
    if target_display:
        cv2.moveWindow(window_name, target_display.x, target_display.y)
        
    # Make window fullscreen
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to capture frame")
                break
            
            # Display frame on the HDMI output
            cv2.imshow(window_name, frame)
            
            # Exit on 'q' key
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except KeyboardInterrupt:
        print("Streaming stopped by user")
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Resources released")

if __name__ == "__main__":
    output_to_hdmi()
