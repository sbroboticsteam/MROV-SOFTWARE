from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor

class Camera(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        
        label = QLabel(" Camera Feeds")
        label.setMaximumHeight(25)

        pal = QPalette();
        pal.setColor(QPalette.Window, QColor("#555555"));
        pal.setColor(QPalette.WindowText, QColor("#ffffff"))
        label.setAutoFillBackground(True); 
        label.setPalette(pal);
        layout.addWidget(label)

        gridlayout = QGridLayout()

        label_1 = QLabel("Camera #1")
        label_1.setAlignment(Qt.AlignRight)

        pal_1 = QPalette();
        pal_1.setColor(QPalette.Window, QColor("#B3B3B3"));
        label_1.setAutoFillBackground(True); 
        label_1.setPalette(pal_1);

        gridlayout.addWidget(label_1, 0, 0, 2, 2)

        label_2 = QLabel("Camera #1")
        label_2.setAlignment(Qt.AlignRight)
        label_2.setPalette(pal_1);
        label_2.setAutoFillBackground(True); 

        gridlayout.addWidget(label_2, 0, 2)

        label_3 = QLabel("Camera #1")
        label_3.setAlignment(Qt.AlignRight)
        label_3.setPalette(pal_1);
        label_3.setAutoFillBackground(True); 

        gridlayout.addWidget(label_3, 1, 2)

        layout.addLayout(gridlayout)

        self.setLayout(layout)
