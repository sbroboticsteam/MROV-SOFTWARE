from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QVBoxLayout, QLabel 

class Component(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("This is a sample widget."))
        layout.addWidget(QLabel("Widgets can be nested within each other."))
        layout.addWidget(QPushButton("You can add elements such as buttons, scrollbars and progress bars to any widget."))
        self.setLayout(layout)