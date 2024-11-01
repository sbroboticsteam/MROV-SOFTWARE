from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout, QPushButton, QFrame, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPainterPath

# controls for minimizing, maximizing and closing widgets (like a window)
class WindowControls(QWidget):
    minimizeClicked = pyqtSignal()
    maximizeClicked = pyqtSignal()
    closeClicked = pyqtSignal()

    def __init__(self, parent=None):
        super(WindowControls, self).__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.minbtn = QPushButton("-")
        self.maxbtn = QPushButton("□")
        self.closebtn = QPushButton("x")

        for btn in [self.minbtn, self.maxbtn, self.closebtn]:
            btn.setFixedSize(20, 20)
            # I HATE CSS!!!!!!
            btn.setStyleSheet("""
                              QPushButton {
                                background-color: #404040;
                                border: none;
                                color: white;
                                font-weight: bold;
                                }
                              QPushButton:hover{
                                background-color: #505050;
                                }
                              """)
        # special stylesheet for X button    
        self.closebtn.setStyleSheet("""
                                    QPushButton{
                                        background-color: #404040;
                                        border: none;
                                        color: white;
                                        font-weight: bold;
                                    }
                                    QPushButton:hover{
                                        background-color: #ff4444;}
                                    """)
        layout.addWidget(self.minbtn)
        layout.addWidget(self.maxbtn)
        layout.addWidget(self.closebtn)

        self.setLayout(layout)

        self.minbtn.clicked.connect(self.minimizeClicked)
        self.maxbtn.clicked.connect(self.maximizeClicked)
        self.closebtn.clicked.connect(self.closeClicked)

# working on widgets that can be moved around and adjusted for size
class AdjustableWidget(QWidget):
    quadrantChanged = pyqtSignal(QWidget, int, int)
    def __init__(self, title="Widget", parent=None, quadrant=0):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(200, 100)
        self.title = title
        self.quadrant = quadrant
        self.minimized=False
        self.maximized=False
        self.og_geometry=None # original geometry
        # self.setStyleSheet("background-color: lightgray;")
        # self.resize(200, 200)
        self.oldpos = None
        self.resizing = False
        self.moving = False
        self.resizemargin = 10
        self.prevsize = self.size()

        self.setupUI()

    def setupUI(self):
        self.mainlayout = QVBoxLayout()
        self.mainlayout.setContentsMargins(0, 0, 0, 0)

        self.title_bar =  QWidget()
        self.title_bar.setStyleSheet("background-color: black")
        self.title_bar.setFixedHeight(30)

        titlelayout = QHBoxLayout()
        titlelayout.setContentsMargins(10, 0, 5, 0)

        self.titlelabel = QLabel(self.title)
        self.titlelabel.setStyleSheet("color: white;")

        self.windowcontrols   = WindowControls()
        self.windowcontrols.minimizeClicked.connect(self.minimizeEvent)
        self.windowcontrols.maximizeClicked.connect(self.maximizeEvent)
        self.windowcontrols.closeClicked.connect(self.closeEvent)

        titlelayout.addWidget(self.titlelabel)
        titlelayout.addStretch()
        titlelayout.addWidget(self.windowcontrols)
        self.title_bar.setLayout(titlelayout)

        self.contentarea =  QWidget()
        self.contentarea.setStyleSheet("background-color: black;")
        self.contentarea.setContentsMargins(10, 10, 10, 10)

        self.mainlayout.addWidget(self.title_bar)
        self.mainlayout.addWidget(self.contentarea)
        self.setLayout(self.mainlayout)

        self.resize(300, 200)
    
    def minimizeEvent(self):
        # if not minimized already, set height of widget to the title bar only
        if not self.minimized:
            self.prevsize = self.size()
            self.setFixedHeight(self.title_bar.height())
            self.minimized=True
        # otherwise keep it as is
        else:
            self.setFixedHeight(self.prevsize.height())
            self.minimized=False
    
    def maximizeEvent(self):
        if not self.maximized:
            self.og_geometry = self.geometry()
            if self.parent():
                self.setGeometry(self.parent().rect())
            self.maximized = True
        else:
            if self.og_geometry:
                self.setGeometry(self.og_geometry)
            self.maximized = False

    def getQuadrantBounds(self):
        if not self.parent():
            return None
        parent_rect = self.parent().rect()
        halfwidth = parent_rect.width() // 2
        halfheight = parent_rect.height() // 2

        quadrant_coords = {
            0: QPoint(0, 0),
            1: QPoint(halfwidth, 0),
            2: QPoint(0,halfheight),
            3: QPoint(halfwidth, halfheight)
        }

        return quadrant_coords
    
    def detectQuadrant(self, pos):
        if not self.parent():
            return self.quadrant
        
        parent_rect = self.parent().rect()
        halfwidth = parent_rect.width() // 2
        halfheight = parent_rect.height() // 2

        x = pos.x() + self.pos().x()
        y = pos.y() + self.pos().y()

        # which quadrant are we in?
        if x < halfwidth:
            if y < halfheight:
                return 0
            else: 
                return 2
        else:
            if y < halfheight:
                return 1
            else:
                return 3
        
    def snaptoQuadrant(self, quadrant):
        bounds= self.getQuadrantBounds()
        if bounds and quadrant in bounds:
            newpos = bounds[quadrant]
            self.move(newpos)

            if self.quadrant != quadrant:
                self.quadrantChanged.emit(self, self.quadrant, quadrant)
                self.quadrant = quadrant


        

    def is_near_border(self, pos):
        return (pos.x() > self.width() - self.resizemargin) or (pos.y() > self.height() - self.resizemargin)

    def resize_widget(self, diff):
        width_new =  self.width() + diff.x()
        height_new = self.height() + diff.y()
        self.resize(width_new, height_new)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 5, 5)
        painter.setPen(QColor('black'))
        painter.fillPath(path, QColor('gray'))
        painter.drawPath(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.oldpos = event.globalPos()
            if self.title_bar.geometry().contains(event.pos()):
                self.moving=True
            elif self.is_near_border(event.pos()) and not self.minimized:
                self.resizing = True

    def mouseMoveEvent(self, event):
        if self.oldpos and not self.maximized:
            diff = QPoint(event.globalPos() - self.oldpos)

            if self.moving:
                newpos = self.pos() + diff
                self.move(newpos)
                newquadrant = self.detectQuadrant(event.pos())
                if newquadrant != self.quadrant:
                    self.snaptoQuadrant(newquadrant)
            elif self.resizing and not self.minimized:
                newwidth = max(self.width() + diff.x(), self.minimumWidth())
                newheight = max(self.height() + diff.y(), self.minimumHeight())
                self.resize(newwidth, newheight)
            self.oldpos = event.globalPos()
    
    def mouseReleaseEvent(self, event):
        self.oldpos, self.resizing, self.moving = None, False, False

# class ExampleAdjustableWindow(AdjustableWidget):
#     def __init__(self):
#         super().__init__()
#         self.setStyleSheet("background-color: lightblue; border: 2px solid darkblue;")
        
#     def resize_widget(self, diff):s
#         width_new = max(self.width() + diff.x(), 100)
#         height_new =max(self.height() + diff.y(), 100)

#         self.resize(width_new, height_new)


#     def paintEvent(self, event):
#         super().paintEvent(event)

#         painter = QPainter.self()
#         painter.setPen(QColor('blue'))
#         painter.setBrush(QColor('lightblue'))
#         painter.drawEllipse(self.width() // 4, self.height() // 4, self.width() // 2, self.height() // 2)
        

   