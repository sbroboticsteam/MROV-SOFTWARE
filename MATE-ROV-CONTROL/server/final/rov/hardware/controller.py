import os
import json
import logging
from typing import Dict, Any


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("rov.log"), logging.StreamHandler()]
)
logger = logging.getLogger("ROV")

# --------------------------- Controller Mapper Class ---------------------------
class ControllerMapper:
    """Maps controller inputs based on user-defined configurations."""
    
    # Default mapping (no remapping)
    DEFAULT_MAPPING = {
        # Analog inputs
        'left_stick_x': 'left_stick_x',
        'left_stick_y': 'left_stick_y',
        'right_stick_x': 'right_stick_x',
        'right_stick_y': 'right_stick_y',
        'left_trigger': 'left_trigger',
        'right_trigger': 'right_trigger',
        
        # Digital inputs
        'a': 'a',
        'b': 'b',
        'x': 'x',
        'y': 'y',
        'lb': 'lb',
        'rb': 'rb',
        'back': 'back',
        'start': 'start',
        
        # D-pad 
        'dpad_x': 'dpad_x',
        'dpad_y': 'dpad_y'
    }
    
    # filepath: /home/itouchedlogourt/Desktop/MROV-SOFTWARE/MATE-ROV-CONTROL/server/final/rov/hardware/controller.py
    def __init__(self):
        self.mapping = self.DEFAULT_MAPPING.copy()
        
        self.config_file = "/home/itouchedlogourt/Desktop/MROV-SOFTWARE/MATE-ROV-CONTROL/server/final/rov/controller_mapping.json"
        
        self.load_mapping()

    def set_mapping(self, source, target):
        """Set a new mapping from source to target"""
        # Translation dictionary from friendly names to internal names
        friendly_to_internal = {
            'strafe left/right': 'left_stick_x',
            'foward/back': 'left_stick_y',
            'turn right/left': 'right_stick_x',
            'tilt foward/back': 'right_stick_y',
            'down': 'left_trigger',
            'up': 'right_trigger',
            'action 0': 'a',
            'action 1': 'b',
            'stowed': 'x',
            'fully out': 'y',
            'out down': 'lb',
            'down': 'rb',
            'rotate right/left': 'dpad_x',
            'open/close': 'dpad_y'
            # Add any other mappings as needed
        }
        
        # Translate BOTH source and target friendly names to internal names
        internal_source = friendly_to_internal.get(source, source)
        internal_target = friendly_to_internal.get(target, target)
        
        # Now check using the translated internal source name
        if internal_source in self.mapping and internal_target in self.DEFAULT_MAPPING.keys():
            self.mapping[internal_source] = internal_target
            logger.info(f"Remapped '{source}' to '{target}' (internal: {internal_source} -> {internal_target})")
            return True
        else:
            logger.error(f"Invalid mapping: '{source}' -> '{target}' (internal: {internal_source} -> {internal_target})")
            return False
    
    def load_mapping(self):
        """Load controller mapping from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    saved_mapping = json.load(f)
                    # Validate the mapping before applying
                    if self._validate_mapping(saved_mapping):
                        self.mapping = saved_mapping
                        logger.info("Controller mapping loaded successfully")
                    else:
                        logger.warning("Invalid mapping in config file, using default mapping")
                        self.mapping = self.DEFAULT_MAPPING.copy()
            else:
                logger.info("No controller mapping found, using default mapping")
        except Exception as e:
            logger.error(f"Error loading controller mapping: {e}")
            self.mapping = self.DEFAULT_MAPPING.copy()
    
    def save_mapping(self):
        """Save the current controller mapping to a file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.mapping, f, indent=2)
            logger.info("Controller mapping saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving controller mapping: {e}")
            return False
    
    def _validate_mapping(self, mapping):
        """Validate that a mapping contains all necessary keys and valid targets"""
        valid_sources = set(self.DEFAULT_MAPPING.keys())
        valid_targets = set(self.DEFAULT_MAPPING.keys())
        
        # Check if all required sources are in the mapping
        if not all(source in mapping for source in valid_sources):
            return False
            
        # Check if all targets are valid
        if not all(target in valid_targets for target in mapping.values()):
            return False
            
        return True
    
    def reset_mapping(self):
        """Reset mapping to default"""
        self.mapping = self.DEFAULT_MAPPING.copy()
        logger.info("Controller mapping reset to default")
        return True
    
    def apply_mapping(self, controller_data):
        """Apply the current mapping to controller data"""
        if not controller_data:
            return {}
            
        mapped_data = {}
        
        # Process each input according to the mapping
        for source, target in self.mapping.items():
            if source in controller_data:
                mapped_data[target] = controller_data[source]
        
        return mapped_data
    
    def get_current_mapping(self):
        """Return the current mapping"""
        return self.mapping.copy()
