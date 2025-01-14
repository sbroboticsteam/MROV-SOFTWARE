# Surface Laptop 

1. surface_laptop.py contains 2 endpoints 
    - GET / - used to signal the float to start the process
    - POST /depth - used by the float to send coordinates
2. The (time, depth) coordinates received from the ESP32 will be stored in coordinates_data.json

# Setup Requirement 
1. Set up a virtual environment for your Python project
  ```
  python -m venv myenv
  ```
2.1 On macOS/Linux
  ```
  source myenv/bin/activate
  ```
2.2 On  Windows
  ```
  myenv\Scripts\activate
  ```
3. Install any missing package (i.e. requests) by 
  ```
  pip install [any missing package]
  ```
4. Run surface_laptop.py 
  ```
  python surface_laptop.py 
  ```
