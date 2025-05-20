import subprocess
import os
import socket
import sys
import platform
import time
import threading
from pathlib import Path
import logging

# For FTP server
try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    FTP_AVAILABLE = True
except ImportError:
    print("pyftpdlib not installed. Run: pip install pyftpdlib")
    FTP_AVAILABLE = False

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

def find_meshlab_executable():
    """
    Automatically finds the MeshLab executable based on the operating system.
    
    Returns:
        str: Path to MeshLab executable or None if not found
    """
    system = platform.system()
    
    if system == "Windows":
        # Common installation paths on Windows
        possible_paths = [
            r"C:\Program Files\VCG\MeshLab\meshlab.exe",
            r"C:\Program Files (x86)\VCG\MeshLab\meshlab.exe",
        ]
    elif system == "Darwin":  # macOS
        possible_paths = [
            "/Applications/MeshLab.app/Contents/MacOS/MeshLab",
            str(Path.home() / "Applications/MeshLab.app/Contents/MacOS/MeshLab"),
        ]
    elif system == "Linux":
        possible_paths = [
            "/usr/bin/meshlab",
            "/usr/local/bin/meshlab",
            "/opt/meshlab/meshlab",
        ]
    else:
        print(f"Unsupported operating system: {system}")
        return None
    
    # Check all possible paths
    for path in possible_paths:
        if os.path.isfile(path):
            print(f"Found MeshLab at: {path}")
            return path
            
    print("MeshLab executable not found automatically.")
    return None

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

class FTPFileHandler(FTPHandler):
    """Custom FTP handler with file notification capabilities"""
    
    def on_file_received(self, file):
        """Called when a file has been received"""
        print(f"\n✓ New file received: {file}")
        filename = os.path.basename(file)
        
        # If it's a PLY file, try to validate and open with MeshLab
        if filename.lower().endswith('.ply'):
            print("PLY file detected, validating...")
            if validate_ply_file(file):
                meshlab_executable = find_meshlab_executable()
                if meshlab_executable:
                    open_meshlab_with_file(meshlab_executable, file)
                else:
                    print("MeshLab not found, skipping automatic opening")
            else:
                print("Invalid PLY file, not opening with MeshLab")

class AnonymousFTPServer:
    """A simple anonymous FTP server for receiving files."""
    
    def __init__(self, root_dir, host='0.0.0.0', port=2121):
        """
        Initialize the FTP server.
        
        Args:
            root_dir (str): Directory to use as the FTP root
            host (str): IP address to bind to
            port (int): Port to listen on
        """
        self.root_dir = os.path.abspath(root_dir)
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None
        
        # Create the directory if it doesn't exist
        os.makedirs(self.root_dir, exist_ok=True)
    
    def start(self):
        """Start the FTP server in a background thread."""
        if not FTP_AVAILABLE:
            print("Error: pyftpdlib module not available. Cannot start FTP server.")
            print("Install with: pip install pyftpdlib")
            return False
            
        if self.server_thread and self.server_thread.is_alive():
            print("FTP server is already running")
            return False
            
        try:
            # Setup the authorizer (anonymous access)
            authorizer = DummyAuthorizer()
            # Add anonymous user with write permissions
            authorizer.add_anonymous(self.root_dir, perm='elradfmwMT')
            
            # Create handler
            handler = FTPFileHandler
            handler.authorizer = authorizer
            handler.banner = "MATE ROV Anonymous FTP Server ready."
            
            # Optionally disable log output from pyftpdlib
            ftpd_logger = logging.getLogger('pyftpdlib')
            ftpd_logger.setLevel(logging.ERROR)  # Only show errors
            
            # Create server
            self.server = FTPServer((self.host, self.port), handler)
            self.server.max_cons = 5
            self.server.max_cons_per_ip = 5
            
            # Start in a thread
            self.server_thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True
            )
            self.server_thread.start()
            
            print(f"\n╔═══════════════════════════════════════════")
            print(f"║ FTP server started!")
            print(f"║ - Host: {self.host}")
            print(f"║ - Port: {self.port}")
            print(f"║ - Directory: {self.root_dir}")
            print(f"║ - Anonymous access enabled (no password needed)")
            print(f"╚═══════════════════════════════════════════")
            print(f"\nOn the sender side (Jetson), use commands like:")
            print(f"ftp {socket.gethostbyname(socket.gethostname())} {self.port}")
            print(f"Username: anonymous")
            print(f"Password: (leave empty or use email)")
            print(f"ftp> put pointcloud.ply\n")
            return True
            
        except Exception as e:
            print(f"Error starting FTP server: {e}")
            return False
    
    def stop(self):
        """Stop the FTP server."""
        if self.server:
            self.server.close_all()
            self.server = None
            print("FTP server stopped")
            return True
        return False

    def list_received_files(self):
        """List files in the FTP directory"""
        files = []
        for item in os.listdir(self.root_dir):
            item_path = os.path.join(self.root_dir, item)
            if os.path.isfile(item_path):
                size = os.path.getsize(item_path)
                modified = os.path.getmtime(item_path)
                modified_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(modified))
                files.append((item, size, modified_time))
        
        if files:
            print(f"\nFiles in {self.root_dir}:")
            print(f"{'Filename':<30} {'Size':<10} {'Modified':<20}")
            print("-" * 60)
            for filename, size, modified in files:
                size_str = f"{size} B"
                if size > 1024:
                    size_str = f"{size/1024:.1f} KB"
                if size > 1024*1024:
                    size_str = f"{size/(1024*1024):.1f} MB"
                print(f"{filename:<30} {size_str:<10} {modified:<20}")
        else:
            print(f"No files in {self.root_dir}")
            
        return files

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
            print("5. Exit")
            
            choice = input("\nEnter your choice (1-5): ")
            
            if choice == '1':
                ftp_server.start()
            elif choice == '2':
                ftp_server.list_received_files()
            elif choice == '3':
                files = ftp_server.list_received_files()
                if files:
                    print("\nEnter the number of the file to open:")
                    for i, (filename, _, _) in enumerate(files, 1):
                        print(f"{i}. {filename}")
                    
                    try:
                        file_choice = int(input("\nFile number (or 0 to cancel): "))
                        if 1 <= file_choice <= len(files):
                            filename = files[file_choice-1][0]
                            file_path = os.path.join(assets_dir, filename)
                            open_meshlab_with_file(meshlab_executable, file_path)
                    except ValueError:
                        print("Invalid choice")
            elif choice == '4':
                ftp_server.stop()
            elif choice == '5':
                if ftp_server.server:
                    ftp_server.stop()
                print("Exiting...")
                break
            else:
                print("Invalid choice, please try again")
                
    except KeyboardInterrupt:
        print("\nReceiver stopped by user")
        if ftp_server.server:
            ftp_server.stop()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command line mode
        if sys.argv[1] == "--start-ftp":
            script_dir = os.path.dirname(os.path.abspath(__file__))
            assets_dir = os.path.join(os.path.dirname(script_dir), "Assets")
            port = int(sys.argv[2]) if len(sys.argv) > 2 else 2121
            
            ftp_server = AnonymousFTPServer(assets_dir, port=port)
            ftp_server.start()
            
            try:
                while True:
                    cmd = input("Enter 'stop' to shutdown the server or 'list' to show files: ")
                    if cmd.lower() == 'stop':
                        ftp_server.stop()
                        break
                    elif cmd.lower() == 'list':
                        ftp_server.list_received_files()
            except KeyboardInterrupt:
                ftp_server.stop()
                print("\nFTP server stopped by user")
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("Available commands:")
            print("  --start-ftp [port]   Start FTP server")
    else:
        # Interactive mode
        main_menu()