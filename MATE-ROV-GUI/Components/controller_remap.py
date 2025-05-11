from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QPushButton, QFrame, QGridLayout)
from PyQt5.QtCore import Qt, pyqtSignal

class ControllerRemappingWidget(QWidget):
    remapRequested = pyqtSignal(str, str)  # source, target
    resetRequested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Controller Remapping")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Explanation
        info = QLabel("Remap controller inputs to different functions")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        
        # Source and target selection
        mapping_frame = QFrame()
        mapping_frame.setFrameShape(QFrame.StyledPanel)
        mapping_frame.setStyleSheet("background-color: #f0f0f0;")
        mapping_layout = QGridLayout(mapping_frame)
        
        # Source selection
        mapping_layout.addWidget(QLabel("Source Input:"), 0, 0)
        self.source_combo = QComboBox()
        self.populate_inputs(self.source_combo)
        mapping_layout.addWidget(self.source_combo, 0, 1)
        
        # Target selection
        mapping_layout.addWidget(QLabel("Target Function:"), 1, 0)
        self.target_combo = QComboBox()
        self.populate_target_inputs(self.target_combo)
        mapping_layout.addWidget(self.target_combo, 1, 1)
        
        layout.addWidget(mapping_frame)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.remap_button = QPushButton("Apply Remapping")
        self.remap_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.remap_button.clicked.connect(self.on_remap_clicked)
        button_layout.addWidget(self.remap_button)
        
        self.reset_button = QPushButton("Reset All Mappings")
        self.reset_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        self.reset_button.clicked.connect(self.on_reset_clicked)
        button_layout.addWidget(self.reset_button)
        
        layout.addLayout(button_layout)
        
        # Current mappings display
        layout.addWidget(QLabel("Current Mappings:"))
        self.mappings_label = QLabel("Default mappings active")
        self.mappings_label.setStyleSheet("background-color: white; padding: 5px;")
        self.mappings_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.mappings_label.setWordWrap(True)
        layout.addWidget(self.mappings_label)
        
        self.setLayout(layout)
    
    def populate_inputs(self, combo):
        """Populate the dropdown with controller inputs"""
        inputs = [
            # Analog inputs
            'left_stick_x', 'left_stick_y', 'right_stick_x', 'right_stick_y',
            'left_trigger', 'right_trigger',
            
            # Digital inputs
            'a', 'b', 'x', 'y', 'lb', 'rb', 'back', 'start',
            
            # D-pad
            'dpad_x', 'dpad_y'
        ]
        combo.addItems(inputs)
    
    def populate_target_inputs(self, combo):
        """Populate the dropdown with controller inputs"""
        inputs = [
            # Analog inputs
            'strafe left/right', 'foward/back', 'turn right/left', 'tilt foward/back',
            'down', 'up',
            
            # Digital inputs
            'action 0', 'action 1', 'stowed', 'fully out', 'out down', 'down', 'action 2', 'action 3',
            
            # D-pad
            'rotate right/left', 'open/close'
        ]
        combo.addItems(inputs)
        
    def on_remap_clicked(self):
        """Handle remap button click"""
        source = self.source_combo.currentText()
        target = self.target_combo.currentText()
        
        if source and target:
            self.remapRequested.emit(source, target)
            # Update the display 
            self.update_mappings_display(source, target)
    
    def on_reset_clicked(self):
        """Handle reset button click"""
        self.resetRequested.emit()
        self.mappings_label.setText("Default mappings active")
    
    def update_mappings_display(self, source, target):
        """Update the display of current mappings"""
        current_text = self.mappings_label.text()
        if current_text == "Default mappings active":
            current_text = ""
            
        new_mapping = f"{source} → {target}"
        
        if current_text:
            current_text += f"<br>{new_mapping}"
        else:
            current_text = new_mapping
            
        self.mappings_label.setText(current_text)