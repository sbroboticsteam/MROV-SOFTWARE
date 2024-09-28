from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel 
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor

class Camera(QWidget):
    def __init__(self):
        super().__init__()
        
        layout = QVBoxLayout()
        label = QLabel("Camera Feeds")
        label.setMaximumHeight(25)

        pal = QPalette();
        pal.setColor(QPalette.Window, QColor("#555555"));
        pal.setColor(QPalette.WindowText, QColor("#ffffff"))
        label.setAutoFillBackground(True); 
        label.setPalette(pal);
        layout.addWidget(label)

        background = QWidget();
        b = QPalette();
        b.setColor(QPalette.Window, QColor("#D9D9D9"));
        background.setAutoFillBackground(True);
        background.setPalette(b)
        layout.addWidget(background)

        layout_1 = QHBoxLayout()
        background.setLayout(layout_1)

        label_1 = QLabel("Camera #1")
        label_1.setAlignment(Qt.AlignRight)

        pal_1 = QPalette();
        pal_1.setColor(QPalette.Window, QColor("#B3B3B3"));
        label_1.setAutoFillBackground(True); 
        label_1.setPalette(pal_1);

        layout_1.addWidget(label_1)

        layout_2 = QVBoxLayout()
        label_2 = QLabel("Camera #1")
        label_2.setAlignment(Qt.AlignRight)
        label_2.setPalette(pal_1);
        label_2.setAutoFillBackground(True);
        layout_2.addWidget(label_2)

        label_3 = QLabel("Camera #1")
        label_3.setAlignment(Qt.AlignRight)
        label_3.setPalette(pal_1);
        label_3.setAutoFillBackground(True);
        layout_2.addWidget(label_3)

        layout_1.addLayout(layout_2)

        self.setLayout(layout)
