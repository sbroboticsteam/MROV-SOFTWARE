from PyQt5.QtWidgets import QGridLayout, QApplication, QWidget, QVBoxLayout, QPushButton, QGroupBox, QLabel
from PyQt5.QtCore import Qt
from PyQt5 import QtCore


class Connectivity(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        label = QLabel("Connectivity")
        label.setStyleSheet("background-color: #555555; color: white; padding: 2.5px;}")
        label.setFixedHeight(25)

        # GroupBox for Connectivity Status Boxes
        group_box = QGroupBox()
        group_box_layout = QVBoxLayout()
        group_box.setStyleSheet("background-color: #D9D9D9;")

        # Raspberry Pi Status
        raspberry_pi = QLabel("Raspberry Pi")
        raspberry_pi.setStyleSheet("background-color: #297A14; color: white; padding: 10px; border-radius: 15px;}")
        raspberry_pi.setAlignment(QtCore.Qt.AlignCenter)

        # Camera 1 Status
        camera1 = QLabel("CAMERA #1")
        camera1.setStyleSheet("background-color: #9A3413; color: white; padding: 10px; border-radius: 15px;}")
        camera1.setAlignment(QtCore.Qt.AlignCenter)

        # Camera 2 Status
        camera2 = QLabel("CAMERA #2")
        camera2.setStyleSheet("background-color: #9A3413; color: white; padding: 10px; border-radius: 15px;}")
        camera2.setAlignment(QtCore.Qt.AlignCenter)

        # X-box Controller Status
        xbox_controller = QLabel("X-box Controller")
        xbox_controller.setStyleSheet("background-color: #297A14; color: white; padding: 10px; border-radius: 15px;}")
        xbox_controller.setAlignment(QtCore.Qt.AlignCenter)

        # Add widgets to group box layout
        group_box_layout.addWidget(raspberry_pi)
        group_box_layout.addWidget(camera1)
        group_box_layout.addWidget(camera2)
        group_box_layout.addWidget(xbox_controller)

        # Set layout for the group box
        group_box.setLayout(group_box_layout)

        # Add label and group box to the main layout
        layout.addWidget(label)
        layout.addWidget(group_box)

        # Set the layout to the main window
        self.setLayout(layout)