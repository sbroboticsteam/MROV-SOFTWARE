import subprocess
import os
import socket
import sys
import platform
import time
import threading
from pathlib import Path
import logging

# ...existing code...

def setup_x11_forwarding(jetson_ip, username="ubuntu"):
    """
    Sets up X11 forwarding from a Jetson running Ubuntu to Windows using VcXsrv.
    
    Args:
        jetson_ip (str): IP address of the Jetson
        username (str): SSH username for the Jetson
    
    Returns:
        bool: True if setup succeeded, False otherwise
    """
    if platform.system() != "Windows":
        print("This function is designed for Windows systems.")
        return False
        
    # Check if VcXsrv is already running
    vcxsrv_running = False
    try:
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq vcxsrv.exe"], 
                              capture_output=True, text=True)
        if "vcxsrv.exe" in result.stdout:
            vcxsrv_running = True
            print("VcXsrv is already running.")
    except Exception as e:
        print(f"Error checking VcXsrv status: {e}")
    
    # Start VcXsrv if not running
    if not vcxsrv_running:
        vcxsrv_paths = [
            r"C:\Program Files\VcXsrv\vcxsrv.exe",
            r"C:\Program Files (x86)\VcXsrv\vcxsrv.exe"
        ]
        
        vcxsrv_found = False
        for path in vcxsrv_paths:
            if os.path.isfile(path):
                try:
                    # Start VcXsrv with proper config for OpenGL support
                    subprocess.Popen([
                        path, 
                        ":0", 
                        "-ac",                # Disable access control
                        "-terminate",         # Terminate when last client disconnects
                        "-lesspointer",       # Hide host pointer when not in window
                        "-multiwindow",       # Use multiple windows
                        "-clipboard",         # Enable clipboard integration
                        "-wgl",               # Enable OpenGL support
                        "-dpi", "auto"        # Auto-detect DPI
                    ])
                    print("Started VcXsrv X server.")
                    vcxsrv_found = True
                    # Give X server time to start
                    time.sleep(2)
                    break
                except Exception as e:
                    print(f"Error starting VcXsrv: {e}")
                    
        if not vcxsrv_found:
            print("VcXsrv not found. Please install from: https://sourceforge.net/projects/vcxsrv/")
            print("After installing, restart this application.")
            return False
    
    # Connect to Jetson with X11 forwarding enabled
    try:
        # Check connectivity first
        print(f"Testing connection to {jetson_ip}...")
        ping_result = subprocess.run(f"ping -n 1 -w 1000 {jetson_ip}", 
                                   shell=True, capture_output=True)
        if ping_result.returncode != 0:
            print(f"Cannot reach Jetson at {jetson_ip}")
            return False
            
        # Set DISPLAY variable for SSH
        env = os.environ.copy()
        env["DISPLAY"] = "localhost:0.0"
        
        # Create a command window with the correct SSH command
        ssh_cmd = f'ssh -X {username}@{jetson_ip}'
        
        # Open a command prompt with the SSH command
        print(f"\n╔═══════════════════════════════════════════")
        print(f"║ Starting SSH with X11 forwarding")
        print(f"║ - Target: {username}@{jetson_ip}")
        print(f"║ - X11 forwarding: Enabled")
        print(f"╚═══════════════════════════════════════════")
        print(f"\nIn the new command window that opens:")
        print(f"1. Enter your password when prompted")
        print(f"2. Run OpenGL applications (e.g., 'glxgears' to test)")
        print(f"3. The application windows will appear on your Windows desktop\n")
        
        # Launch a new command window with the SSH command
        subprocess.Popen(f'start cmd /k "set DISPLAY=localhost:0.0 && {ssh_cmd}"', shell=True)
        
        return True
    except Exception as e:
        print(f"Error setting up X11 forwarding: {e}")
        return False

def test_x11_connection(jetson_ip, username="ubuntu"):
    """
    Tests X11 connection by running glxgears on the Jetson.
    
    Args:
        jetson_ip (str): IP address of the Jetson
        username (str): SSH username for the Jetson
    """
    try:
        # Set DISPLAY variable for SSH
        env = os.environ.copy()
        env["DISPLAY"] = "localhost:0.0"
        
        # SSH command to run glxgears
        ssh_cmd = f'ssh -X {username}@{jetson_ip} "DISPLAY=:0 glxgears"'
        
        print(f"Testing X11 connection by running glxgears...")
        print(f"Command: {ssh_cmd}")
        
        # Run the command
        subprocess.Popen(ssh_cmd, shell=True, env=env)
        
    except Exception as e:
        print(f"Error testing X11 connection: {e}")
        return False

def main_menu():
    """Display a simple menu for the FTP server"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(os.path.dirname(script_dir), "Assets")
    
    # Find MeshLab executable
    meshlab_executable = find_meshlab_executable() or r"C:\Program Files\VCG\MeshLab\meshlab.exe"
    
    # Create FTP server
    ftp_server = AnonymousFTPServer(assets_dir, port=2121)
    
    try:
        while True:
            print("\n===== MATE ROV Pointcloud Receiver =====")
            print("1. Start FTP Server")
            print("2. List Received Files")
            print("3. Open File with MeshLab")
            print("4. Stop FTP Server")
            print("5. Connect to Jetson (X11 Forwarding)")
            print("6. Test X11 Connection (Run glxgears)")
            print("7. Exit")
            
            choice = input("\nEnter your choice (1-7): ")
            
            if choice == '1':
                ftp_server.start()
            elif choice == '2':
                ftp_server.list_received_files()
            elif choice == '3':
                # ...existing code...
            elif choice == '4':
                ftp_server.stop()
            elif choice == '5':
                jetson_ip = input("Enter Jetson IP address: ")
                username = input("Enter Jetson username [ubuntu]: ") or "ubuntu"
                setup_x11_forwarding(jetson_ip, username)
            elif choice == '6':
                jetson_ip = input("Enter Jetson IP address: ")
                username = input("Enter Jetson username [ubuntu]: ") or "ubuntu"
                test_x11_connection(jetson_ip, username)
            elif choice == '7':
                if ftp_server.server:
                    ftp_server.stop()
                print("Exiting...")
                break
            else:
                print("Invalid choice, please try again")
                
    # ...rest of function unchanged...