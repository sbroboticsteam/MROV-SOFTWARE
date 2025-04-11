import cv2

def main():
    # Open a connection to the default camera (0)
    cap = cv2.VideoCapture(1)
    
    if not cap.isOpened():
        print("Cannot open camera")
        return

    while True:
        # Read a frame
        ret, frame = cap.read()
        
        # If frame read was not successful, break out of loop
        if not ret:
            print("Can't receive frame (stream end?). Exiting ...")
            break
        
        # Display the frame
        cv2.imshow('Camera Stream', frame)
        
        # Press 'q' to exit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Release the capture and close windows
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
