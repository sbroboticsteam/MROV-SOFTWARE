from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout, QPushButton, QFrame, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QCloseEvent
from Components.speedpanel import SpeedPanel
from Components.camera import MainWindow as CameraWindow
from Components.connectivity import Connectivity
from Components.depth_time import DepthTimeWidget
from Components.controller import ControllerSender

from Components.leak import LeakSensor
# from Components.controller_sensitivity import ControllerSensitivity, AdjustableControllerSensivitity
from Components.controller_sensitivity import ControllerSensitivity
# Add imports for the individual camera widgets
from Components.camera_widgets import USB1CameraWindow, USB2CameraWindow, ZEDCameraWindow
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
    def __init__(self, title="Widget", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMinimumSize(200, 100)
        self.title = title
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
        self.windowcontrols.closeClicked.connect(self.handleClose)

        titlelayout.addWidget(self.titlelabel)
        titlelayout.addStretch()
        titlelayout.addWidget(self.windowcontrols)
        self.title_bar.setLayout(titlelayout)


        if self.title == "Speed Panel":
            widget = SpeedPanel()
        elif self.title == "USB Camera":
            print("DEBUG - Creating CameraWindow for USB Camera")
            try:
                widget = CameraWindow()
                print("DEBUG - CameraWindow created successfully")
            except Exception as e:
                print(f"DEBUG - Error creating CameraWindow: {e}")
                import traceback
                traceback.print_exc()
                # Create a fallback widget with error information
                error_widget = QWidget()
                error_layout = QVBoxLayout(error_widget)
                error_label = QLabel(f"Error creating camera: {str(e)}")
                error_label.setStyleSheet("color: red; background-color: #ffeeee; padding: 10px;")
                error_layout.addWidget(error_label)
                widget = error_widget
        # Add new camera widget types
        elif self.title == "USB Camera 1":
            try:
                widget = USB1CameraWindow()
                print("USB Camera 1 created successfully")
            except Exception as e:
                print(f"Error creating USB Camera 1: {e}")
                import traceback
                traceback.print_exc()
                widget = self._create_error_widget(f"Error creating USB Camera 1: {str(e)}")
        elif self.title == "USB Camera 2":
            try:
                widget = USB2CameraWindow()
                print("USB Camera 2 created successfully")
            except Exception as e:
                print(f"Error creating USB Camera 2: {e}")
                import traceback
                traceback.print_exc()
                widget = self._create_error_widget(f"Error creating USB Camera 2: {str(e)}")
        elif self.title == "ZED Camera":
            try:
                widget = ZEDCameraWindow()
                print("ZED Camera created successfully")
            except Exception as e:
                print(f"Error creating ZED Camera: {e}")
                import traceback
                traceback.print_exc()
                widget = self._create_error_widget(f"Error creating ZED Camera: {str(e)}")
        elif self.title == "Connectivity":
            widget = Connectivity()
        elif self.title == "Controller Sensitivity":
            widget = ControllerSensitivity(self)
        elif self.title=='Depth-Time Graph':
            widget=DepthTimeWidget()
        elif self.title=='Controller Sender':
            widget=ControllerSender()
        # elif self.title=='Network Connection':
        #     widget=NetworkConnectionWidget()
        
        
        
        elif self.title == "Leak Sensor":
            widget = LeakSensor()
            # Store the widget in self.content before accessing it
            self.content = widget
            
            # Connect signals if the parent has a data_handler
            if hasattr(self.parent(), 'data_handler') and self.parent().data_handler:
                # Connect to leak data updates
                self.parent().data_handler.signals.leak_update.connect(self.content.update_status)
                
                # Connect to emergency alerts if the signal exists
                if hasattr(self.parent().data_handler.signals, 'emergency_update'):
                    self.parent().data_handler.signals.emergency_update.connect(self.content.update_from_emergency)
                
                # Connect to depth telemetry (which contains leak data in your ROV code)
                self.parent().data_handler.signals.depth_update.connect(self.content.update_from_telemetry)
        else:
            widget = QWidget()

        self.contentarea =  widget
        # self.contentarea.setStyleSheet("background-color: black;")
        # self.contentarea.setContentsMargins(10, 10, 10, 10)

        self.mainlayout.addWidget(self.title_bar)
        self.mainlayout.addWidget(self.contentarea)
        self.setLayout(self.mainlayout)

        self.resize(300, 200)

    def _create_error_widget(self, error_message):
        """Create an error widget with the given message"""
        error_widget = QWidget()
        error_layout = QVBoxLayout(error_widget)
        error_label = QLabel(error_message)
        error_label.setStyleSheet("color: red; background-color: #ffeeee; padding: 10px;")
        error_label.setWordWrap(True)
        error_layout.addWidget(error_label)
        return error_widget
    
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

    def handleClose(self):
        # Check if the content area has a close method
        if hasattr(self.contentarea, 'close'):
            try:
                self.contentarea.close()
            except Exception as e:
                print(f"Error closing widget content: {e}")
        self.close()
        
    def closeEvent(self, event: QCloseEvent):
        if self.parent() and hasattr(self.parent, 'widgets'):
            if self in self.parent().widgets:
                self.parent.widgets.remove(self)
        event.accept()


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
            self.raise_()
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
            elif self.resizing and not self.minimized:
                newwidth = max(self.width() + diff.x(), self.minimumWidth())
                newheight = max(self.height() + diff.y(), self.minimumHeight())
                self.resize(newwidth, newheight)
            self.oldpos = event.globalPos()
   
    def mouseReleaseEvent(self, event):
        self.oldpos, self.resizing, self.moving = None, False, False


