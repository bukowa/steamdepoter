import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QVBoxLayout, QWidget, QSplitter
from PyQt6.QtCore import Qt

from src.db import Database
from src.gui.tabs import GamesTab, DepotsTab, ManifestsTab, ManifestFilesTab
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
        self.manifests_tab = ManifestsTab(self.session, self.console, self.db)
        self.files_tab = ManifestFilesTab(self.session, self.console, self.db)

        # Connect signals for automatic refresh
        self.games_tab.data_changed.connect(self.refresh_all_tabs)
        self.depots_tab.data_changed.connect(self.refresh_all_tabs)
        self.manifests_tab.data_changed.connect(self.refresh_all_tabs)
        self.files_tab.data_changed.connect(self.refresh_all_tabs)

        self.tabs.addTab(self.games_tab, "Games")
        self.tabs.addTab(self.depots_tab, "Depots")
        self.tabs.addTab(self.manifests_tab, "Manifests")
        self.tabs.addTab(self.files_tab, "Manifest Files")

        splitter.addWidget(self.tabs)
        splitter.addWidget(self.console)
        
        # Initial sizes: 70% tabs, 30% console
        splitter.setSizes([560, 240])

        layout.addWidget(splitter)

    def refresh_all_tabs(self):
        """Refresh data in all tabs and ensure session is up to date."""
        self.session.expire_all()
        self.games_tab.refresh_data()
        self.depots_tab.refresh_data()
        self.manifests_tab.refresh_data()
        self.files_tab.refresh_data()

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
