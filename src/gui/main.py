import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QVBoxLayout, QWidget, QSplitter
from PyQt6.QtCore import Qt

from src.db import Database
from src.gui.tabs import GamesTab, DepotsTab
from src.gui.console import ConsolePanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SteamDepoter2")
        self.setGeometry(100, 100, 1200, 800)

        # Initialize database
        self.db = Database()
        self.db.create_tables()
        self.session = self.db.get_session()

        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create splitter for tabs and console
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Create tab widget
        self.tabs = QTabWidget()

        # Console Panel
        self.console = ConsolePanel()

        self.games_tab = GamesTab(self.session, self.console)
        self.depots_tab = DepotsTab(self.session, self.console)

        self.tabs.addTab(self.games_tab, "Games")
        self.tabs.addTab(self.depots_tab, "Depots")

        splitter.addWidget(self.tabs)
        splitter.addWidget(self.console)
        
        # Initial sizes: 70% tabs, 30% console
        splitter.setSizes([560, 240])

        layout.addWidget(splitter)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

