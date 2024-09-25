from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QVBoxLayout
from Components.component import Component

import sys

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MATE ROV Dashboard")
        layout = QVBoxLayout()
        button = QPushButton("Underwater robot go brrr")
        layout.addWidget(button)

        component = Component()
        layout.addWidget(component)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()