# main.py

import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from src.pyroland.gui.ui.mainwindow import Ui_MainWindow  # replace with your generated class/name
from src.pyroland.controllers.main_controller import MainController


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # instantiate the UI object and attach it to this window
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    controller = MainController(window)
    window.show()
    sys.exit(app.exec())
