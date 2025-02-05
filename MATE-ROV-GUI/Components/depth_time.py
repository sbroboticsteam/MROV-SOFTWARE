from PyQt5.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QGroupBox, QLabel, QPushButton
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import pyqtgraph as pg
import requests, json

class DataFetchThread(QThread):
    # handle http requests w/o messing with UI

    data_recv=pyqtSignal(dict) #data received
    error=pyqtSignal(str)

    def run(self):
        try:
            response=requests.get('http://localhost:8000')
            if response.status_code==200:
                self.data_recv.emit(response.json())
            else:
                self.error.emit(f'Error: status code {response.status_code}')
        except requests.RequestException as r:
            self.error.emit(f'connection error: {str(r)}')

class DepthTimeWidget(QWidget):
    def __init__(self, title="Depth vs Time", quadrant=4):
        super().__init__() #Initialize class
        self.setWindowTitle("Depth vs Time")

        self.fetch_thread=None

        self.time_data=[]
        self.depth_data=[]
        self.plot=None

        #Set layout
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.graph=pg.PlotWidget()
        self.graph.setBackground('white')
        self.graph.setTitle('Depth vs Time')
        self.graph.setLabel('left', 'Depth(m)')
        self.graph.setLabel('bottom', 'Time(s)')
        self.graph.showGrid(x=True,y=True)

        self.startButton=QPushButton('Start Float')
        self.drawButton=QPushButton('Draw')

        self.layout.addWidget(self.graph)
        self.layout.addWidget(self.startButton)
        self.layout.addWidget(self.drawButton)

        self.startButton.clicked.connect(self.startFloat)
        self.drawButton.clicked.connect(self.drawGraph)

    def startFloat(self):
        self.fetch_thread=DataFetchThread()
        self.fetch_thread.data_recv.connect(self.handleData)
        self.fetch_thread.error.connect(self.handleError)
        self.fetch_thread.start()
        self.startButton.setEnabled(False)
    
    def handleData(self, data):
        self.startButton.setEnabled(True)
        self.updatePlot(data)
    
    def handleError(self, error):
        self.startButton.setEnabled(True)
        print(f'Error: {error}')

    def drawGraph(self):
        try:
            with open('MATE-ROV-GUI\coordinates_data.json', 'r') as file:
                data=json.load(file)
                self.updatePlot(data)
        except Exception as e:
            print(f'Error loading JSON file:{str(e)}')

    def updatePlot(self, data):
        if self.plot is not None:
            self.graph.removeItem(self.plot)

        try:
            coords=data.get('coordinates',[])

            self.time_data=[coord['time'] for coord in coords]
            self.depth_data=[coord['depth'] for coord in coords]

            self.plot=self.graph.plot(self.time_data, self.depth_data, pen=pg.mkPen(color=(0,0,255), width=2))

            self.graph.setXRange(min(self.time_data), max(self.time_data))
            self.graph.setYRange(min(self.depth_data), max(self.depth_data))

        except Exception as e:
            print(f'Error updating data:{str(e)}')




