from PyQt5.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QGroupBox, QLabel
from PyQt5.QtCore import Qt

class DepthTimeWidget(QWidget):
    def __init__(self, title="Depth vs Time", quadrant=4):
        super().__init__() #Initialize class
        self.setWindowTitle("Depth vs Time")

        #Set layout
        layout = QVBoxLayout()
        label = QLabel("Depth vs Time")
        layout.addWidget(label)
        self.setLayout(layout)