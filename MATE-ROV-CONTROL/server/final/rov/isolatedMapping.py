import logging
import json
import os
import time
import threading
from hardware.controller import ControllerMapper
from hardware.ethernet_man import EthernetManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("remap_server_test.log"), logging.StreamHandler()]
)
logger = logging.getLogger("RemapServer")

class RemapTester:
    """Test class to handle controller remapping over Ethernet"""
    
    def __init__(self):
        logger.info("Initializing RemapTester...")
        
        # Create controller mapper
        self.controller_mapper = ControllerMapper()
        logger.info(f"Controller config file: {self.controller_mapper.config_file}")
        logger.info(f"Config file exists: {os.path.exists(self.controller_mapper.config_file)}")
        
        # Create Ethernet manager without callback
        self.ethernet = EthernetManager()
        # Set the callback after creation
        self.ethernet.set_control_callback(self.process_command)
        
        # Initialize button state tracking
        self.prev_button_states = {}
        self.running = False
        
    def start(self):
        """Start the test server"""
        logger.info("Starting RemapTester server...")
        self.ethernet.start_control_server()
        self.running = True
        self._main_loop()
        
    def shutdown(self):
        """Shutdown the test server"""
        logger.info("Shutting down RemapTester...")
        self.running = False
        self.ethernet.shutdown()
        
    def _main_loop(self):
        """Main processing loop"""
        logger.info("Server is running. Connect from your laptop to test remapping...")
        # Just keep the server running and processing commands via callback
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
            self.running = False
        
    def process_command(self, command_data):
        """Process commands received from Ethernet connection"""
        command_processed = False
        
        if 'controller' in command_data:
            # Store original controller data for remapping
            original_controller = command_data['controller']
            
            # Debug received controller data
            # logger.info(f"Received controller data: {original_controller}")
            
            # Apply controller mapping
            controller = self.controller_mapper.apply_mapping(original_controller)
            
            # Extract button states for easier access
            a_button = controller.get('a', 0)
            b_button = controller.get('b', 0)
            x_button = controller.get('x', 0)
            y_button = controller.get('y', 0)
            lb_button = controller.get('lb', 0)
            rb_button = controller.get('rb', 0)
            
            # Get previous button states
            prev_a = self.prev_button_states.get('a', 0)
            prev_b = self.prev_button_states.get('b', 0)
            prev_x = self.prev_button_states.get('x', 0)
            prev_y = self.prev_button_states.get('y', 0)
            prev_lb = self.prev_button_states.get('lb', 0)
            prev_rb = self.prev_button_states.get('rb', 0)
            
            # Enhanced remapping handling as in your ROV class
            for source, target in self.controller_mapper.mapping.items():
                # Check if the source is in the original controller data AND is pressed
                if source in original_controller:
                    # If this source input is active in the original controller
                    if original_controller[source] == 1:
                        # Update the mapped button state accordingly
                        if target == 'a': a_button = 1
                        elif target == 'b': b_button = 1
                        elif target == 'x': x_button = 1
                        elif target == 'y': y_button = 1
                        elif target == 'lb': lb_button = 1
                        elif target == 'rb': rb_button = 1
                    
                    # Also handle previous button states for edge detection
                    if source in self.prev_button_states and self.prev_button_states.get(source, 0) == 1:
                        # Update the previous mapped button state accordingly
                        if target == 'a': prev_a = 1
                        elif target == 'b': prev_b = 1
                        elif target == 'x': prev_x = 1
                        elif target == 'y': prev_y = 1
                        elif target == 'lb': prev_lb = 1
                        elif target == 'rb': prev_rb = 1
            
            # Log the buttons that would be activated
            button_actions = {}
            
            if a_button == 1:
                button_actions['a'] = "Open claw"
                command_processed = True
                
            if b_button == 1:
                current_time = time.time()
                
                # First press, record time
                if prev_b == 0:
                    self.b_button_press_time = current_time
                    logger.info("B button pressed - hold for 3 seconds to initialize thrusters")
                
                # Check if button has been held for 3+ seconds
                if (current_time - self.b_button_press_time >= 3.0):  # Removed the "not"
                    logger.info("B button held for 3 seconds, initializing thrusters...")
                    # self.initialize_thrusters()
                    # Reset timer to prevent repeated initialization
                    self.b_button_press_time = current_time + 100  # Set far in the future
                    command_processed = True
                
            if x_button == 1 and prev_x == 0:
                button_actions['x'] = "Stow arm"
                command_processed = True
                
            if y_button == 1 and prev_y == 0:
                button_actions['y'] = "Fully extend arm"
                command_processed = True
                
            if lb_button == 1 and prev_lb == 0:
                button_actions['lb'] = "Arm out and down"
                command_processed = True
                
            if rb_button == 1 and prev_rb == 0:
                button_actions['rb'] = "Arm fully down"
                command_processed = True
            
            # Log active buttons
            if button_actions:
                logger.info(f"Button actions: {button_actions}")
            
            # Update previous button states for next iteration
            self.prev_button_states = {
                'a': a_button,
                'b': b_button,
                'x': x_button,
                'y': y_button,
                'lb': lb_button,
                'rb': rb_button
            }
            
            # Special commands for server management
            if 'remap' in command_data:
                remap_data = command_data['remap']
                if 'source' in remap_data and 'target' in remap_data:
                    source = remap_data['source']
                    target = remap_data['target']
                    success = self.controller_mapper.set_mapping(source, target)
                    logger.info(f"Remapping {source} -> {target}: {'Success' if success else 'Failed'}")

                    if success:
                        # Save the mapping to file
                        save_result = self.controller_mapper.save_mapping()
                        logger.info(f"Save result: {'Success' if save_result else 'Failed'}")
                        
                        # Verify the file was updated
                        try:
                            # Force reload from file to verify
                            test_mapper = ControllerMapper()
                            logger.info(f"Reloaded mapping from file, rb maps to: {test_mapper.mapping.get('rb', 'unknown')}")
                        except Exception as e:
                            logger.error(f"Error verifying saved mapping: {e}")
                
                if 'save' in remap_data and remap_data['save']:
                    success = self.controller_mapper.save_mapping()
                    logger.info(f"Saving mapping: {'Success' if success else 'Failed'}")
                
                if 'reset' in remap_data and remap_data['reset']:
                    self.controller_mapper.reset_mapping()
                    self.controller_mapper.save_mapping()
                    logger.info("Mapping reset to default")
        
        return command_processed

def main():
    """Main entry point"""
    server = RemapTester()
    try:
        server.start()
    except Exception as e:
        logger.error(f"Error in RemapTester: {e}")
    finally:
        server.shutdown()

if __name__ == "__main__":
    main()