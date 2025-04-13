camera_ip='192.168.1.198'

# Common RTSP URL patterns
rtsp_patterns = [
    f"rtsp://{camera_ip}:554/stream",
    f"rtsp://{camera_ip}:554/live",
    f"rtsp://{camera_ip}:554/h264",
    f"rtsp://{camera_ip}:554/av0_0",
    f"rtsp://{camera_ip}:554/cam/realmonitor",
    f"rtsp://{camera_ip}:554/channel1",
    f"rtsp://{camera_ip}/11",
    f"rtsp://admin:admin@{camera_ip}/media/video1",
    f"rtsp://{camera_ip}/mpeg4"
]

# Common MJPEG URL patterns
mjpeg_patterns = [
    f"http://{camera_ip}/mjpg/video.mjpg",
    f"http://{camera_ip}/video/mjpg.cgi",
    f"http://{camera_ip}/cgi-bin/mjpeg",
    f"http://{camera_ip}/mjpeg",
    f"http://{camera_ip}/video.cgi",
    f"http://{camera_ip}/video.mjpeg",
    f"http://{camera_ip}/mjpegstream"
]

# Snapshot URL patterns (for continuous polling)
snapshot_patterns = [
    f"http://{camera_ip}/snapshot.cgi",
    f"http://{camera_ip}/image.jpg",
    f"http://{camera_ip}/cgi-bin/snapshot.cgi",
    f"http://{camera_ip}/cgi/jpg/image.cgi",
    f"http://{camera_ip}/jpg/image.jpg"
]

def discover_camera_stream(camera_ip, username="admin", password="admin"):
    """Try common URL patterns to find the camera's stream URL"""
    import requests
    from requests.auth import HTTPBasicAuth
    import cv2
    
    auth = HTTPBasicAuth(username, password)
    
    # Function to check if URL is accessible
    def check_http_url(url):
        try:
            response = requests.head(url, auth=auth, timeout=2)
            return response.status_code == 200
        except:
            return False
    
    # Function to check if RTSP URL is valid
    def check_rtsp_url(url):
        try:
            cap = cv2.VideoCapture(url)
            result = cap.isOpened()
            if result:
                ret, _ = cap.read()
                result = ret
            cap.release()
            return result
        except:
            return False
    
    # Try RTSP URLs (higher quality and lower latency)
    print("Checking RTSP URLs...")
    for pattern in rtsp_patterns:
        url = pattern
        if username and password and "@" not in url:
            url = url.replace("rtsp://", f"rtsp://{username}:{password}@")
        print(f"Trying {url}")
        if check_rtsp_url(url):
            print(f"Found working RTSP URL: {url}")
            return {"type": "rtsp", "url": url}
    
    # Try MJPEG URLs
    print("Checking MJPEG URLs...")
    for url in mjpeg_patterns:
        print(f"Trying {url}")
        if check_http_url(url):
            print(f"Found working MJPEG URL: {url}")
            return {"type": "mjpeg", "url": url}
    
    # Try snapshot URLs as a last resort
    print("Checking snapshot URLs...")
    for url in snapshot_patterns:
        print(f"Trying {url}")
        if check_http_url(url):
            print(f"Found working snapshot URL: {url}")
            return {"type": "snapshot", "url": url}
    
    return None

print(discover_camera_stream(camera_ip, 'admin', ''))