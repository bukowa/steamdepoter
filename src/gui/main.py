import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget

from src.db import Database
from src.gui.tabs import GamesTab, DepotsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SteamDepoter2")
        self.setGeometry(100, 100, 1000, 700)

        # Initialize database
        self.db = Database()
        self.db.create_tables()
        self.session = self.db.get_session()

        # Create tab widget
        tabs = QTabWidget()

        games_tab = GamesTab(self.session)
        depots_tab = DepotsTab(self.session)

        tabs.addTab(games_tab, "Games")
        tabs.addTab(depots_tab, "Depots")

        self.setCentralWidget(tabs)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

