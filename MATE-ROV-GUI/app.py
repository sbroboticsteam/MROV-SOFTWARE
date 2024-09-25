from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton

import sys

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MATE ROV Dashboard")
        button = QPushButton("Underwater robot go brrr")

        self.setCentralWidget(button)

app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()