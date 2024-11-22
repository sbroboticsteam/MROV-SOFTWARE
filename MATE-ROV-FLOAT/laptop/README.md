# Surface Laptop 

1. surface_laptop.py contains 2 endpoints 
    - GET /
    - POST /depth
2. The (time, depth) coordinates received from the ESP32 will be stored in coordinates_data.json

# Setup Requirement 

1. To set up a virtual environment for your Python project, follow these steps:
  ```
  python -m venv myenv
  ```
    - On macOS/Linux
    ```
    source myenv/bin/activate
    ```
    - On  Windows
    ```
    myenv\Scripts\activate
    ```
  ```
  pip install [any missing packages]
  ```

2. Run surface_laptop.py 
  ```
  python surface_laptop.py 
  ```