import json
import os

class PresetManager:
    def __init__(self, app_dir):
        self.app_dir = app_dir
        self.presets_dir = os.path.join(app_dir, 'presets')
        
        # Create presets directory if it doesn't exist
        if not os.path.exists(self.presets_dir):
            os.makedirs(self.presets_dir)
            
        # Create default presets if none exist
        if not os.listdir(self.presets_dir):
            self.create_default_presets()
    
    def create_default_presets(self):
        """Create default preset configurations"""
        camera_preset = {
            "name": "Camera View",
            "pages": [
                {
                    "name": "Dual Camera Layout",
                    "widgets": [
                        {
                            "type": "USB Camera 1",
                            "geometry": [50, 50, 600, 400]
                        },
                        {
                            "type": "USB Camera 2",
                            "geometry": [660, 50, 600, 400]
                        },
                        {
                            "type": "Speed Panel",
                            "geometry": [50, 460, 350, 250]
                        }
                    ]
                }
            ]
        }
        
        # mission_preset = {
        #     "name": "Mission Control",
        #     "pages": [
        #         {
        #             "name": "Command Center",
        #             "widgets": [
        #                 {
        #                     "type": "USB Camera 1",
        #                     "geometry": [50, 50, 500, 350]
        #                 },
        #                 {
        #                     "type": "Depth-Time Graph",
        #                     "geometry": [560, 50, 600, 350]
        #                 },
        #                 {
        #                     "type": "Controller Sender",
        #                     "geometry": [50, 410, 400, 300]
        #                 },
        #                 {
        #                     "type": "Leak Sensor",
        #                     "geometry": [460, 410, 300, 200]
        #                 },
        #                 {
        #                     "type": "Connectivity",
        #                     "geometry": [770, 410, 350, 250]
        #                 }
        #             ]
        #         }
        #     ]
        # }
        
        # Save the presets
        self.save_preset("camera_view.json", camera_preset)
        # self.save_preset("mission_control.json", mission_preset)
    
    def save_preset(self, filename, preset_data):
        """Save a preset configuration to file"""
        filepath = os.path.join(self.presets_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(preset_data, f, indent=2)
    
    def load_preset(self, filename):
        """Load a preset configuration from file"""
        filepath = os.path.join(self.presets_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
        return None
    
    def get_available_presets(self):
        """Get list of available preset configurations"""
        presets = []
        for filename in os.listdir(self.presets_dir):
            if filename.endswith('.json'):
                preset = self.load_preset(filename)
                if preset and "name" in preset:
                    presets.append({
                        "filename": filename,
                        "name": preset["name"]
                    })
        return presets