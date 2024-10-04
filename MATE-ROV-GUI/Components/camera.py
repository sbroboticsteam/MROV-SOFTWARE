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

        box = QWidget()
        box.setStyleSheet("background-color: white; border: 1px solid lightgray;")

        label_1 = QLabel("Camera #1")
        label_1.setAlignment(Qt.AlignRight)
        pal_1 = QPalette();
        pal_1.setColor(QPalette.Window, QColor("#B3B3B3"));
        label_1.setAutoFillBackground(True); 
        label_1.setPalette(pal_1);
        label_1.setFixedWidth(100)
        label_1.setFixedHeight(25)

        gridlayout.addWidget(box, 0, 0, 4, 4)
        gridlayout.addWidget(label_1, 0, 3)

        box2 = QWidget()
        box2.setStyleSheet("background-color: white; border: 1px solid lightgray;")

        label_2 = QLabel("Camera #1")
        label_2.setAlignment(Qt.AlignRight)
        label_2.setAutoFillBackground(True); 
        label_2.setPalette(pal_1);
        label_2.setFixedWidth(100)
        label_2.setFixedHeight(25)

        gridlayout.addWidget(box2, 0, 4, 2, 2)
        gridlayout.addWidget(label_2, 0, 5)

        box3 = QWidget()
        box3.setStyleSheet("background-color: white; border: 1px solid lightgray;")

        label_3 = QLabel("Camera #1")
        label_3.setAlignment(Qt.AlignRight)
        label_3.setAutoFillBackground(True); 
        label_3.setPalette(pal_1);
        label_3.setFixedWidth(100)
        label_3.setFixedHeight(25)

        gridlayout.addWidget(box3, 2, 4, 2, 2)
        gridlayout.addWidget(label_3, 2, 5)

        layout.addLayout(gridlayout)

        self.setLayout(layout)
