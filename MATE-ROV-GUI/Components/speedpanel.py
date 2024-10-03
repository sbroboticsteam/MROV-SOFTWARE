from PyQt5.QtWidgets import QWidget, QVBoxLayout, QSlider, QGroupBox, QLabel
from PyQt5.QtCore import Qt

class SpeedPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        
        group_box = QGroupBox("Speed")
        
        group_layout = QVBoxLayout()
        
        self.slider1 = QSlider(Qt.Horizontal)
        self.slider2 = QSlider(Qt.Horizontal)
        self.slider3 = QSlider(Qt.Horizontal)
        
        group_layout.addWidget(self.slider1)
        group_layout.addWidget(self.slider2)
        group_layout.addWidget(self.slider3)
        
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        
        self.setLayout(layout)