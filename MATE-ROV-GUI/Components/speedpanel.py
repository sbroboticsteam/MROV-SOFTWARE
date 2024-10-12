from PyQt5.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QGroupBox
from PyQt5.QtCore import Qt

class SpeedPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(300, 200)
        
        layout = QVBoxLayout()
        
        group_box = QGroupBox("Speed")
        group_box.setStyleSheet("QGroupBox { background-color: #ddd; color: black; }")
        
        group_layout = QVBoxLayout()
        
        self.progress_bar1 = QProgressBar()
        self.progress_bar2 = QProgressBar()
        self.progress_bar3 = QProgressBar()
        
        self.progress_bar1.setRange(0, 100)
        self.progress_bar2.setRange(0, 100)
        self.progress_bar3.setRange(0, 100)
        
        self.progress_bar1.setStyleSheet("QProgressBar { background-color: #3d3d3d; color: white; } QProgressBar::chunk { background-color: #a9a9a9; }")
        self.progress_bar2.setStyleSheet("QProgressBar { background-color: #3d3d3d; color: white; } QProgressBar::chunk { background-color: #a9a9a9; }")
        self.progress_bar3.setStyleSheet("QProgressBar { background-color: #3d3d3d; color: white; } QProgressBar::chunk { background-color: #a9a9a9; }")
        
        group_layout.addWidget(self.progress_bar1)
        group_layout.addWidget(self.progress_bar2)
        group_layout.addWidget(self.progress_bar3)
        
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        
        self.setLayout(layout)
    
    def update_speeds(self, speed1, speed2, speed3):
        self.progress_bar1.setValue(speed1)
        self.progress_bar2.setValue(speed2)
        self.progress_bar3.setValue(speed3)
        
        self.progress_bar1.setFormat(f"x-axis: {speed1:.1f}")
        self.progress_bar2.setFormat(f"y-axis: {speed2:.1f}")
        self.progress_bar3.setFormat(f"z-axis: {speed3:.1f}")