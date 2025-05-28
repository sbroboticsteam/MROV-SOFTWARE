import pygame
import math


def main():
    pygame.init()  # Initialize all Pygame modules, including event system

    # Then initialize joysticks, etc.
    pygame.joystick.init()

    # Now the rest of your code that calls pygame.event.pump() or read_inputs()

if __name__ == "__main__":
    main()


class ControllerMapping:
    """
    Manages hardware input -> logical action mappings.
    """

    def __init__(self, initial_mapping=None):
        # If no mapping is provided, use a default dictionary
        self.mapping = initial_mapping or {
            # Axes indices
            0: "move_x",
            1: "move_y",
            2: "rotate_x",
            3: "rotate_y",
            4: "left_trigger",
            5: "right_trigger",
            # Buttons (optional)
            ("button", 0): "openClaw",
            ("button", 1): "closeClaw"
        }

    def remap_action(self, old_action, new_action):
        """
        Reassign any hardware input that is mapped to old_action 
        so it becomes new_action.
        """
        found = False
        for hw_input, logic_action in list(self.mapping.items()):
            if logic_action == old_action:
                self.mapping[hw_input] = new_action
                print(f"Remapped {hw_input} from '{old_action}' to '{new_action}'")
                found = True
                break
        if not found:
            print(f"Warning: No hardware input found for action '{old_action}'.")

class ControllerState:
    """
    Holds and updates the current values of each logical action.
    """

    def __init__(self, deadzone=0.1):
        self.deadzone = deadzone
        self.state = {}  # { logical_action: current_value }

    def normalize_axis(self, value):
        """Normalize axis values to [-1.0, 1.0] with a deadzone."""
        normalized = value
        if abs(normalized) < self.deadzone:
            return 0.0
        return normalized

    def normalize_trigger(self, value):
        """Normalize trigger values to [0.0, 1.0]."""
        return value

    def set_value(self, action, raw_value, is_trigger=False):
        """Update the state for a given logical action."""
        if is_trigger:
            self.state[action] = self.normalize_trigger(raw_value)
        else:
            self.state[action] = self.normalize_axis(raw_value)

    def get_value(self, action):
        """Retrieve the current value for a logical action."""
        return self.state.get(action, 0.0)


import pygame

class RemappableController:
    """
    Reads hardware inputs via PyGame, applies a ControllerMapping,
    and updates a ControllerState.
    """

    def __init__(self, mapping=None, deadzone=0.1):
        # If no mapping is provided, use a default ControllerMapping instance
        self.mapping = mapping or ControllerMapping()
        self.state_manager = ControllerState(deadzone=deadzone)

        pygame.joystick.init()
        self.joysticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
        if not self.joysticks:
            print("Warning: No joysticks found.")
        else:
            for js in self.joysticks:
                js.init()

    def read_inputs(self):
        """Reads raw input from the first joystick, updates the state."""
        pygame.event.pump()  # Process queued events
        
        if not self.joysticks:
            return self.state_manager.state  # Return empty or default state

        js = self.joysticks[0]

        # Axes
        for axis_idx in range(js.get_numaxes()):
            hw_action = (axis_idx)  # e.g., 0, 1, 2, ...
            if hw_action in self.mapping.mapping:
                logic_action = self.mapping.mapping[hw_action]
                raw_val = js.get_axis(axis_idx)

                # Decide if it's a trigger or normal axis
                is_trigger = (axis_idx in [4, 5])  # Example for triggers
                self.state_manager.set_value(logic_action, raw_val, is_trigger=is_trigger)

        # Buttons
        for btn_idx in range(js.get_numbuttons()):
            hw_action = ("button", btn_idx)
            if hw_action in self.mapping.mapping:
                logic_action = self.mapping.mapping[hw_action]
                btn_val = js.get_button(btn_idx)
                # Buttons are typically 0 or 1
                self.state_manager.set_value(logic_action, btn_val, is_trigger=False)

        return dict(self.state_manager.state)

    def remap_action(self, old_action, new_action):
        """Expose remapping at the controller level."""
        self.mapping.remap_action(old_action, new_action)
        
        
class RobotController:
    """
    Example class demonstrating how you'd integrate the remappable controller
    into a higher-level robot logic.
    """
    def __init__(self, mapping=None, deadzone=0.1):
        self.controller = RemappableController(mapping, deadzone=deadzone)

    def run(self):
        """Main loop for retrieving input and performing actions."""
        try:
            while True:
                controls = self.controller.read_inputs()
                self.handle_controls(controls)

        except KeyboardInterrupt:
            print("Exiting RobotController.")

    def handle_controls(self, controls):
        """
        Process the current state dictionary to drive motors or actuators.
        For example: 
          'move_x' => control left-right,
          'move_y' => control forward-back,
          'openClaw', 'closeClaw' => set claw motor, etc.
        """
        # Example usage:
        move_x = controls.get('move_x', 0.0)
        move_y = controls.get('move_y', 0.0)
        open_claw = controls.get('openClaw', 0)
        close_claw = controls.get('closeClaw', 0)

        # Print or send to motors
        print(f"move_x: {move_x:.2f}, move_y: {move_y:.2f}, open_claw: {open_claw}, close_claw: {close_claw}")
        # ... call your real motor functions here ...

    def remap_action(self, old_action, new_action):
        """Expose remapping at the robot control level."""
        self.controller.remap_action(old_action, new_action)

if __name__ == "__main__":
    # Create a default or custom mapping if you wish
    mapping_obj = ControllerMapping({
    0: "move_x",
    1: "move_y",
    ("button", 0): "openClaw"
    })
    robot = RobotController(mapping=mapping_obj)
    robot.remap_action("openClaw", "lightOn")
    robot.run()



