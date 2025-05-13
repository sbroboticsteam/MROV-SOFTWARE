import json
import os
import time
import threading
import socket
import requests
from PyQt5.QtCore import QObject, pyqtSignal, QThread
import websocket

class DataUpdateSignals(QObject):
    """Signals for data updates"""
    connectivity_update = pyqtSignal(dict)
    speed_update = pyqtSignal(dict)
    controller_update = pyqtSignal(dict)
    depth_update = pyqtSignal(dict)
    generic_update = pyqtSignal(str, dict)  # data_type, data
    
    
    leak_update = pyqtSignal(dict)
    
class FileMonitorThread(QThread):
    """Monitor JSON files for changes"""
    file_changed = pyqtSignal(str, dict)  # file_type, data
    
    def __init__(self, file_paths=None):
        super().__init__()
        self.file_paths = file_paths or {}
        self.running = False
        self.last_modified = {}
        
    def run(self):
        self.running = True
        
        # Initialize last modified times
        for file_type, path in self.file_paths.items():
            if os.path.exists(path):
                self.last_modified[file_type] = os.path.getmtime(path)
        
        while self.running:
            for file_type, path in self.file_paths.items():
                if os.path.exists(path):
                    current_mtime = os.path.getmtime(path)
                    
                    # Check if file was modified
                    if file_type not in self.last_modified or current_mtime > self.last_modified[file_type]:
                        try:
                            with open(path, 'r') as f:
                                data = json.load(f)
                                self.file_changed.emit(file_type, data)
                        except json.JSONDecodeError:
                            print(f"Error decoding JSON from {path}")
                        except Exception as e:
                            print(f"Error reading {path}: {str(e)}")
                        
                        self.last_modified[file_type] = current_mtime
            
            # Check every 1 second
            time.sleep(1)
    
    def stop(self):
        self.running = False
        self.wait()

class WebSocketThread(QThread):
    """Handle WebSocket connections for real-time data"""
    message_received = pyqtSignal(dict)
    connection_status = pyqtSignal(bool)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.ws = None
        self.running = False
    
    def run(self):
        self.running = True
        
        # Define WebSocket callbacks
        def on_message(ws, message):
            try:
                data = json.loads(message)
                self.message_received.emit(data)
            except json.JSONDecodeError:
                print(f"Error decoding WebSocket message: {message}")
            
        def on_error(ws, error):
            print(f"WebSocket error: {error}")
            self.connection_status.emit(False)
            
        def on_close(ws, close_status_code, close_msg):
            print("WebSocket connection closed")
            self.connection_status.emit(False)
            
        def on_open(ws):
            print(f"WebSocket connection established to {self.url}")
            self.connection_status.emit(True)
        
        # Create WebSocket connection
        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(
            self.url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        # Keep reconnecting if connection fails
        while self.running:
            self.ws.run_forever(ping_interval=30)
            if not self.running:
                break
            print("WebSocket disconnected. Reconnecting in 5 seconds...")
            time.sleep(5)
    
    def send_message(self, message):
        """Send a message through the WebSocket connection"""
        if self.ws:
            self.ws.send(message)
    
    def stop(self):
        """Stop the WebSocket thread"""
        self.running = False
        if self.ws:
            self.ws.close()
        self.wait()

class HTTPPollerThread(QThread):
    """Poll HTTP endpoints for data"""
    data_received = pyqtSignal(str, dict)  # endpoint_name, data
    
    def __init__(self, endpoints=None, interval=2):
        super().__init__()
        self.endpoints = endpoints or {}  # {name: {url, headers}}
        self.interval = interval
        self.running = False
    
    def run(self):
        self.running = True
        
        while self.running:
            for name, config in self.endpoints.items():
                try:
                    response = requests.get(
                        config['url'],
                        headers=config.get('headers', {}),
                        timeout=3
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        self.data_received.emit(name, data)
                    else:
                        print(f"HTTP error for {name}: {response.status_code}")
                        
                except requests.RequestException as e:
                    print(f"Request failed for {name}: {str(e)}")
                except json.JSONDecodeError:
                    print(f"Error decoding JSON from {name}")
                except Exception as e:
                    print(f"Error with endpoint {name}: {str(e)}")
            
            time.sleep(self.interval)
    
    def stop(self):
        self.running = False
        self.wait()

class DataHandler:
    """Centralized data handler for all data sources"""
    def __init__(self):
        self.signals = DataUpdateSignals()
        
        # Last received data for each type
        self.data_cache = {
            'connectivity': {},
            'speed': {},
            'controller': {},
            'depth': {}
        }
        
        # Base directory for JSON files
        self.json_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'json_formats')
        if not os.path.exists(self.json_dir):
            os.makedirs(self.json_dir)
        
        # Initialize file monitor
        self.file_paths = {
            'speed': os.path.join(self.json_dir, 'speed_panel_sample.json'),
            'connectivity': os.path.join(self.json_dir, 'connectivity_sample.json'),
            'controller': os.path.join(self.json_dir, 'controller_sensitivity_sample.json'),
            'depth': os.path.join(self.json_dir, 'depth_time_sample.json')
        }
        self.file_monitor = None
        
        # Initialize WebSocket
        self.websocket_thread = None
        
        # Initialize HTTP poller
        self.http_poller = None
        
        # Network configuration
        self.network_config = self._load_network_config()
    
    def _load_network_config(self):
        """Load network configuration"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'network_config.json')
        
        default_config = {
            'websocket_url': 'ws://localhost:8080',
            'http_endpoints': {
                'speed': {'url': 'http://localhost:8000/speed'},
                'depth': {'url': 'http://localhost:8000/depth'}
            }
        }
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # Save default config if none exists
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=4)
        
        return default_config
    
    def start_file_monitoring(self):
        """Start monitoring JSON files for changes"""
        if self.file_monitor is None or not self.file_monitor.isRunning():
            self.file_monitor = FileMonitorThread(self.file_paths)
            self.file_monitor.file_changed.connect(self._handle_file_update)
            self.file_monitor.start()
    
    def start_websocket(self):
        """Start WebSocket connection"""
        if self.websocket_thread is None or not self.websocket_thread.isRunning():
            url = self.network_config.get('websocket_url', 'ws://localhost:8080')
            self.websocket_thread = WebSocketThread(url)
            self.websocket_thread.message_received.connect(self._handle_websocket_message)
            self.websocket_thread.start()
    
    def start_http_polling(self):
        """Start polling HTTP endpoints"""
        if self.http_poller is None or not self.http_poller.isRunning():
            endpoints = self.network_config.get('http_endpoints', {})
            self.http_poller = HTTPPollerThread(endpoints)
            self.http_poller.data_received.connect(self._handle_http_data)
            self.http_poller.start()
    
    def start_all(self):
        """Start all data sources"""
        self.start_file_monitoring()
        self.start_websocket()
        self.start_http_polling()
    
    def stop_all(self):
        """Stop all data sources"""
        if self.file_monitor and self.file_monitor.isRunning():
            self.file_monitor.stop()
            
        if self.websocket_thread and self.websocket_thread.isRunning():
            self.websocket_thread.stop()
        
        if self.http_poller and self.http_poller.isRunning():
            self.http_poller.stop()
    
    def _handle_file_update(self, file_type, data):
        """Handle file updates"""
        # Cache the data
        self.data_cache[file_type] = data
        
        # Emit appropriate signal
        if file_type == 'speed':
            self.signals.speed_update.emit(data)
        elif file_type == 'connectivity':
            self.signals.connectivity_update.emit(data)
        elif file_type == 'controller':
            self.signals.controller_update.emit(data)
        elif file_type == 'depth':
            self.signals.depth_update.emit(data)
            
        # Also emit a generic update
        self.signals.generic_update.emit(file_type, data)
    
    def _handle_websocket_message(self, data):
        """Handle WebSocket messages"""
        if 'emergency' in data and data['emergency'] == True:
            if hasattr(self.signals, 'emergency_update'):
                self.signals.emergency_update.emit(data)
        if 'type' in data:
            data_type = data['type']
            payload = data.get('payload', {})
            
            # Cache the data
            if data_type in self.data_cache:
                self.data_cache[data_type] = payload
            
            # Emit appropriate signal
            if data_type == 'speed':
                self.signals.speed_update.emit(payload)
            elif data_type == 'connectivity':
                self.signals.connectivity_update.emit(payload)
            elif data_type == 'controller':
                self.signals.controller_update.emit(payload)
            elif data_type == 'depth':
                self.signals.depth_update.emit(payload)
            
            
            
            
            
            if data_type == 'depth' and 'leak_sensor' in payload:
                self.signals.leak_update.emit(payload['leak_sensor'])
            
            
            
            
            # Also emit a generic update
            self.signals.generic_update.emit(data_type, payload)
    
    def _handle_http_data(self, endpoint_name, data):
        """Handle HTTP data"""
        # Map endpoint name to data type if they differ
        data_type = endpoint_name
        
        # Cache the data
        if data_type in self.data_cache:
            self.data_cache[data_type] = data
        
        # Emit appropriate signal
        if data_type == 'speed':
            self.signals.speed_update.emit(data)
        elif data_type == 'connectivity':
            self.signals.connectivity_update.emit(data)
        elif data_type == 'controller':
            self.signals.controller_update.emit(data)
        elif data_type == 'depth':
            self.signals.depth_update.emit(data)
            
        # Also emit a generic update
        self.signals.generic_update.emit(data_type, data)
    
    def get_cached_data(self, data_type):
        """Get the last cached data for a specific type"""
        return self.data_cache.get(data_type, {})
    
    def send_websocket_message(self, message):
        """Send a message through WebSocket"""
        if self.websocket_thread and self.websocket_thread.isRunning():
            if isinstance(message, dict):
                message = json.dumps(message)
            self.websocket_thread.send_message(message)