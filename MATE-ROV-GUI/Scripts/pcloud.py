import subprocess
import os
import socket
import sys
import platform
import time
import threading
from pathlib import Path

def open_meshlab_with_file(meshlab_path, file_path):
    """
    Opens MeshLab with the specified file.
    
    Args:
        meshlab_path (str): Full path to the MeshLab executable
        file_path (str): Path to the mesh file to open
    """
    # Convert to absolute paths
    meshlab_path = os.path.abspath(meshlab_path)
    file_path = os.path.abspath(file_path)
    
    # Check if paths exist
    if not os.path.isfile(meshlab_path):
        print(f"Error: MeshLab executable not found at {meshlab_path}")
        return False
    
    if not os.path.isfile(file_path):
        print(f"Error: File not found at {file_path}")
        return False
    
    try:
        # Launch MeshLab with the file
        subprocess.Popen([meshlab_path, file_path])
        print(f"Opening {file_path} with MeshLab...")
        return True
        
    except Exception as e:
        print(f"Error launching MeshLab: {e}")
        return False

def receive_pointcloud_file(save_path, host='0.0.0.0', port=9999):
    """
    Receives a pointcloud file over TCP socket and saves it to the specified path.
    
    Args:
        save_path (str): Path to save the received file
        host (str): IP address to listen on (default: '0.0.0.0' - all interfaces)
        port (int): Port to listen on
        
    Returns:
        bool: True if file was received successfully, False otherwise
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        # Create a TCP socket server
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            s.listen(1)
            
            print(f"Waiting for pointcloud file on {host}:{port}...")

            # Accept a connection
            conn, addr = s.accept()
            with conn:
                print(f"Connection from {addr}")
                
                # First receive the file size
                file_size_bytes = conn.recv(8)
                file_size = int.from_bytes(file_size_bytes, byteorder='big')
                
                print(f"Receiving file of size {file_size} bytes...")

                # Then receive the file data
                with open(save_path, 'wb') as f:
                    bytes_received = 0
                    while bytes_received < file_size:
                        chunk = conn.recv(min(4096, file_size - bytes_received))
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_received += len(chunk)
                        
                        # Print progress
                        progress = (bytes_received / file_size) * 100
                        print(f"Progress: {progress:.1f}%", end='\r')
                
                print(f"\nFile saved to {save_path}")
                return True
    except Exception as e:
        print(f"Error receiving file: {e}")
        return False

def validate_ply_file(file_path):
    """
    Checks if a PLY file has valid header structure.
    
    Args:
        file_path (str): Path to the PLY file
        
    Returns:
        bool: True if the file has a valid PLY header, False otherwise
    """
    try:
        with open(file_path, 'rb') as f:
            # Check for PLY magic number
            header = f.read(3).decode('ascii', errors='ignore')
            if header != 'ply':
                print(f"Error: File doesn't start with 'ply' header: {header}")
                return False

             # Reset and read full header
            f.seek(0)
            header_lines = []
            line = b''
            while line != b'end_header\n':
                line = f.readline()
                if not line:
                    print("Error: Reached end of file without finding end_header")
                    return False
                header_lines.append(line.decode('ascii', errors='ignore').strip())
                if len(header_lines) > 100:  # Sanity check
                    print("Error: Header too long, possibly invalid format")
                    return False
            
            print("PLY header found:")
            for line in header_lines:
                print(f"  {line}")
            return True
                
    except Exception as e:
        print(f"Error validating PLY file: {e}")
        return False
    
def start_receiver(save_path, host='0.0.0.0', port=9999):
    """Starts the receiver in a separate thread"""
    receiver_thread = threading.Thread(
        target=receiver_loop,
        args=(save_path, host, port),
        daemon=True
    )
    receiver_thread.start()
    return receiver_thread

def receiver_loop(save_path, host, port):
    """Continuously receives files"""
    while True:
        received = receive_pointcloud_file(save_path, host, port)
        if received:
            # Notify the main thread that a new file is available
            # You could use a queue or event for this in a more complex application
            print("\nNew pointcloud file received and ready for viewing.")
        time.sleep(1)  # Small delay before listening again

if __name__ == "__main__":
    # Define your known paths here
    meshlab_executable = r"C:\Program Files\VCG\MeshLab\meshlab.exe"  # Replace with your actual path
    pointcloud_file = r"MATE-ROV-GUI\Assets\Pointcloud.ply"  # Replace with your actual path

    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(os.path.dirname(script_dir), "Assets")
    #pointcloud_file = os.path.join(assets_dir, "received_pointcloud.ply")

    txt_file_path = os.path.join(assets_dir, "received_pointcloud.txt")
    HOST='0.0.0.0' #LISTEN EVERYTHING BY DEFAULT
    PORT=8080

    receive_pointcloud_file(txt_file_path, HOST, PORT)
    # # Start receiver in a loop
    # if receive_pointcloud_file(pointcloud_file, HOST, PORT):
    #     # Validate the file before opening
    #     open_meshlab_with_file(meshlab_executable, pointcloud_file)
    #         print("Not opening MeshLab because file appears to be invalid")

    # Open MeshLab with the pointcloud file
    #open_meshlab_with_file(meshlab_executable, pointcloud_file)