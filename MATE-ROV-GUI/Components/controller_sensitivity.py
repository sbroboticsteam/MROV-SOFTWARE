from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QSlider

class ControllerSensitivity(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        name = QLabel("Controller Sensitivity")
        joystick_label = QLabel("Joystick")
        self.joystick_slider = QSlider(Qt.Horizontal)
        self.joystick_slider.setMinimum(1)
        self.joystick_slider.setMaximum(100)
        self.joystick_slider.setValue(50)
        self.joystick_slider.valueChanged.connect(self.joystick_changed)  # 

        button_label = QLabel("Button")
        self.button_slider = QSlider(Qt.Horizontal)
        self.button_slider.setMinimum(1)
        self.button_slider.setMaximum(100)
        self.button_slider.setValue(50)
        self.button_slider.valueChanged.connect(self.button_changed)  # 

        layout.addWidget(name)
        layout.addWidget(joystick_label)
        layout.addWidget(self.joystick_slider)
        layout.addWidget(button_label)
        layout.addWidget(self.button_slider)

    def joystick_changed(self, value):
        print(f"Joystick sensitivity changed to: {value}")  # Prints to terminal

    def button_changed(self, value):
        print(f"Button sensitivity changed to: {value}")  # Prints to terminal