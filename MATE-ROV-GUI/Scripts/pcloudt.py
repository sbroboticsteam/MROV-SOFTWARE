import subprocess
import os

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

if __name__ == "__main__":
    # Define your known paths here
    meshlab_executable = r"C:\Program Files\VCG\MeshLab\meshlab.exe"  # Replace with your actual path
    pointcloud_file = r"C:\Users\vince\OneDrive\Documents\1PARA\1Projects\Robotics_Project\MATE-ROV-GUI\MROV-SOFTWARE\MATE-ROV-GUI\Assets\Pointcloud.ply"
    
    # Open MeshLab with the pointcloud file
    open_meshlab_with_file(meshlab_executable, pointcloud_file)