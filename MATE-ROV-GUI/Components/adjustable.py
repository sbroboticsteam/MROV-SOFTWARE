from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QPainter, QColor

# working on widgets that can be moved around and adjusted for size
class AdjustableWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("background-color: lightgray;")
        self.resize(200, 200)
        self.oldpos = None
        self.resizing = False
        self.moving = False
        self.resizemargin = 10
    
    def is_near_border(self, pos):
        return pos.x() > self.width() - self.resizemargin or pos.y() > self.height() - self.resizemargin

    def resize_widget(self, diff):
        width_new =  self.width() + diff.x()
        height_new = self.height() + diff.y()
        self.resize(width_new, height_new)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QColor('black'))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.oldpos = event.globalPos()
            if self.is_near_border(event.pos()):
                self.resizing = True
            else:
                self.moving = True

    def mouseMoveEvent(self, event):
        if self.oldpos:
            diff = QPoint(event.globalPos() - self.oldpos)
            if self.resize:
                self.resize_widget(diff)
            if self.moving:
                self.move(self.pos() + diff)
            self.oldpos = event.globalPos()
    
    def mouseReleaseEvent(self, event):
        self.oldpos, self.resizing, self.moving = None, False, False

class ExampleAdjustableWindow(AdjustableWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: lightblue; border: 2px solid darkblue;")
        
    def resize_widget(self, diff):
        width_new = max(self.width() + diff.x(), 100)
        height_new =max(self.height() + diff.y(), 100)

        self.resize(width_new, height_new)


    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter.self()
        painter.setPen(QColor('blue'))
        painter.setBrush(QColor('lightblue'))
        painter.drawEllipse(self.width() // 4, self.height() // 4, self.width() // 2, self.height() // 2)
        

   