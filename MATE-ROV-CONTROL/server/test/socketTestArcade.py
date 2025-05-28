import os
import sys
import json
import time
import logging
import threading

# Add the parent directory to the path so we can import our modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(parent_dir)

# Import the EthernetManager
from ethernet_manager import EthernetManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ROV-Test")

def arcadeDrive3(x, y, rx, ry, rT, lT) -> list[float]:
    """
    Convert controller inputs to thruster values
    x: left/right movement (left stick X)
    y: forward/backward movement (left stick Y)
    rx: yaw/turning (right stick X)
    ry: pitch control (right stick Y)
    rT: up movement (right trigger)
    lT: down movement (left trigger)
    """
    # Calculate vertical thrust from triggers
    PWM = rT - lT
    
    # Calculate horizontal thruster values with X, Y, and rotation inputs
    frontLeft = y + x + rx  # 2
    frontRight = y - x - rx  # 3
    backRight = -y - x + rx  # 4  
    backLeft = -y + x - rx   # 1
    
    # Create initial data array for horizontal thrusters
    data = [-frontLeft, -frontRight, -backLeft, -backRight]
    
    # Normalize thruster values if any exceeds limits
    max_val = max(abs(val) for val in data)
    if max_val > 1.0:
        data = [val/max_val for val in data]
    
    # Apply pitch control to vertical thrusters
    # When ry is positive (stick down), front should go down, back should go up
    front_vertical = -PWM - ry
    back_vertical = -PWM + ry
    
    # Add vertical thrusters to the data array
    data.append(front_vertical)  # Front Left Up
    data.append(front_vertical)  # Front Right Up
    data.append(back_vertical)   # Back Right Up
    data.append(back_vertical)   # Back Left Up
    
    return data

def test_arcade_drive():
    """Test the arcade drive function with various inputs"""
    logger.info("Testing Arcade Drive function...")
    
    # Test cases with expected inputs and outputs
    test_cases = [
        # [left_x, left_y, right_x, right_y, right_trigger, left_trigger]
        [0.0, 0.5, 0.0, 0.0, 0.0, 0.0],      # Forward
        [0.0, -0.5, 0.0, 0.0, 0.0, 0.0],     # Backward
        [0.5, 0.0, 0.0, 0.0, 0.0, 0.0],      # Strafe right
        [-0.5, 0.0, 0.0, 0.0, 0.0, 0.0],     # Strafe left
        [0.0, 0.0, 0.5, 0.0, 0.0, 0.0],      # Rotate right
        [0.0, 0.0, -0.5, 0.0, 0.0, 0.0],     # Rotate left
        [0.0, 0.0, 0.0, 0.5, 0.0, 0.0],      # Pitch down
        [0.0, 0.0, 0.0, -0.5, 0.0, 0.0],     # Pitch up
        [0.0, 0.0, 0.0, 0.0, 0.5, 0.0],      # Rise
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.5],      # Dive
        [0.3, 0.3, 0.2, 0.1, 0.7, 0.2],      # Combined movement
    ]
    
    for i, inputs in enumerate(test_cases):
        outputs = arcadeDrive3(*inputs)
        logger.info(f"Test {i+1}:")
        logger.info(f"  Inputs: left_x={inputs[0]:.2f}, left_y={inputs[1]:.2f}, right_x={inputs[2]:.2f}, "
                    f"right_y={inputs[3]:.2f}, right_trigger={inputs[4]:.2f}, left_trigger={inputs[5]:.2f}")
        logger.info(f"  Outputs: {[f'{x:.2f}' for x in outputs]}")
        logger.info(f"  Horizontal: {[f'{x:.2f}' for x in outputs[:4]]}")
        logger.info(f"  Vertical: {[f'{x:.2f}' for x in outputs[4:]]}")
        logger.info("------------------------")

class ROVTestController:
    """Test class for simulating ROV control with EthernetManager"""
    
    def __init__(self):
        self.ethernet = EthernetManager(control_ip='192.168.1.237', control_port=4891)
        self.ethernet.set_control_callback(self.process_command)
        self.motor_values = [0.0] * 8
        self.running = False
        self.last_command_time = 0
        
    def process_command(self, command_data):
        """Process received command data."""
        self.last_command_time = time.time()
        
        # Print the received command
        logger.info(f"Received command: {json.dumps(command_data, indent=2)}")
        
        # Handle the controller data format
        if 'controller' in command_data:
            controller = command_data['controller']
            
            # Extract controller values
            left_x = controller.get('left_stick_x', 0.0)
            left_y = controller.get('left_stick_y', 0.0)
            right_x = controller.get('right_stick_x', 0.0)
            right_y = controller.get('right_stick_y', 0.0)
            left_trigger = controller.get('left_trigger', 0.0)
            right_trigger = controller.get('right_trigger', 0.0)
            
            # Apply deadzone to avoid drift
            def apply_deadzone(value, deadzone=0.05):
                return 0.0 if abs(value) < deadzone else value
                
            left_x = apply_deadzone(left_x)
            left_y = apply_deadzone(left_y)
            right_x = apply_deadzone(right_x)
            right_y = apply_deadzone(right_y)
            
            # Convert controller values to motor values
            self.motor_values = arcadeDrive3(
                left_x, 
                -left_y,  # Invert Y-axis
                right_x,
                -right_y, # Invert Y-axis
                right_trigger,
                left_trigger
            )
            
            logger.info(f"Controller inputs processed:")
            logger.info(f"  left_x={left_x:.2f}, left_y={-left_y:.2f}, right_x={right_x:.2f}, "
                     f"right_y={-right_y:.2f}, right_trigger={right_trigger:.2f}, left_trigger={left_trigger:.2f}")
            logger.info(f"  Motor values: {[f'{x:.2f}' for x in self.motor_values]}")
            
            # Send back telemetry for testing bidirectional communication
            self.send_telemetry()
    
    def send_telemetry(self):
        """Send telemetry data back to the client"""
        telemetry = {
            "timestamp": time.time(),
            "motor_values": [float(f"{x:.2f}") for x in self.motor_values],
            "status": "OK"
        }
        self.ethernet.send_telemetry(telemetry)
    
    def run(self):
        """Run the test controller"""
        logger.info("Starting ROV Test Controller...")
        
        # Start the Ethernet Manager
        if not self.ethernet.start_control_server():
            logger.error("Failed to start Ethernet Manager")
            return
        
        self.running = True
        logger.info("ROV Test Controller running. Waiting for client connection...")
        
        try:
            while self.running:
                time.sleep(0.5)
                
                # Periodically send telemetry even without commands
                if self.ethernet.connected:
                    self.send_telemetry()
                    
                # Print connection status every 5 seconds
                if int(time.time()) % 5 == 0:
                    status = "CONNECTED" if self.ethernet.connected else "WAITING FOR CONNECTION"
                    client = self.ethernet.client_address if self.ethernet.connected else "None"
                    logger.info(f"Status: {status} | Client: {client}")
                    
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Shut down the test controller"""
        self.running = False
        self.ethernet.shutdown()
        logger.info("ROV Test Controller shut down")

def main():
    """Main function to run the tests"""
    print("\n=== ETHERNET MANAGER AND ARCADE DRIVE TEST ===\n")
    
    # First test the arcade drive function
    test_arcade_drive()
    
    # Now test the Ethernet Manager with arcade drive
    print("\n=== Starting UDP Server Test ===")
    print("This will listen for incoming controller data on 192.168.1.237:4891")
    print("Use a test client to send controller data to this address")
    print("Press Ctrl+C to exit\n")
    
    controller = ROVTestController()
    controller.run()

if __name__ == "__main__":
    main()