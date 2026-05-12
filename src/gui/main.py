import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QVBoxLayout, QWidget, QSplitter
from PyQt6.QtCore import Qt

from src.db import Database
from src.gui.tabs import GamesTab, DepotsTab
from src.gui.console import ConsolePanel
from src.gui.dialogs import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SteamDepoter2")
        self.setGeometry(100, 100, 1200, 800)

        # Initialize database
        self.db = Database()
        self.db.create_tables()
        self.session = self.db.get_session()

        self.init_menu()

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

        self.games_tab = GamesTab(self.session, self.console, self.db)
        self.depots_tab = DepotsTab(self.session, self.console, self.db)

        self.tabs.addTab(self.games_tab, "Games")
        self.tabs.addTab(self.depots_tab, "Depots")

        splitter.addWidget(self.tabs)
        splitter.addWidget(self.console)
        
        # Initial sizes: 70% tabs, 30% console
        splitter.setSizes([560, 240])

        layout.addWidget(splitter)

    def init_menu(self):
        menubar = self.menuBar()
        settings_menu = menubar.addMenu("Settings")
        
        options_action = settings_menu.addAction("Options")
        options_action.triggered.connect(self.on_open_settings)

    def on_open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
