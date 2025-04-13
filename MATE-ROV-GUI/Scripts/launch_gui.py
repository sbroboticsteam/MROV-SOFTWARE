from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt
import sys

class SimpleWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Window")
        self.resize(300, 200)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Add a title
        title = QLabel("Script Execution Test")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Add a message
        message = QLabel("This window was launched from the MATE ROV Dashboard")
        message.setAlignment(Qt.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message)
        
        # Add a simple button
        self.button = QPushButton("Click Me")
        self.button.clicked.connect(self.on_button_click)
        layout.addWidget(self.button)
        
        # Status label
        self.status = QLabel("Ready")
        self.status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status)
        
        self.setLayout(layout)
        
    def on_button_click(self):
        self.status.setText("Button was clicked!")
        self.status.setStyleSheet("color: green; font-weight: bold;")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SimpleWindow()
    window.show()
    sys.exit(app.exec_())