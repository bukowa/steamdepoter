import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QVBoxLayout, QWidget, QSplitter
from PyQt6.QtCore import Qt

from src.db import Database
from src.gui.tabs import LibraryTab, BrowserTab
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

        self.library_tab = LibraryTab(self.session, self.console, self.db)
        self.browser_tab = BrowserTab(self.session, self.console, self.db)

        # Connect signals for automatic refresh
        self.library_tab.data_changed.connect(self.refresh_all_tabs)
        self.browser_tab.data_changed.connect(self.refresh_all_tabs)
        self.browser_tab.task_queue_finished.connect(self.on_browser_tasks_finished)

        # Connect navigation signal
        self.library_tab.open_steamdb.connect(self.on_open_steamdb)
        self.library_tab.open_steamdb_depot.connect(self.on_open_steamdb_depot)
        self.library_tab.parse_depots_steamdb.connect(self.on_parse_depots_steamdb)
        self.library_tab.scrape_manifests_steamdb.connect(self.on_scrape_manifests_steamdb)

        self.tabs.addTab(self.library_tab, "Library")
        self.tabs.addTab(self.browser_tab, "Browser")

        splitter.addWidget(self.tabs)
        splitter.addWidget(self.console)
        
        # Initial sizes: 70% tabs, 30% console
        splitter.setSizes([560, 240])

        layout.addWidget(splitter)

    def refresh_all_tabs(self):
        """Refresh data in all tabs and ensure session is up to date."""
        self.session.expire_all()
        self.library_tab.refresh_data()
        self.browser_tab.refresh_data()

    def on_browser_tasks_finished(self):
        """Switch back to the Library tab when browser tasks are complete."""
        self.tabs.setCurrentWidget(self.library_tab)

    def on_open_steamdb(self, app_id: str):
        """Switch to browser tab and load app_id."""
        self.tabs.setCurrentWidget(self.browser_tab)
        self.browser_tab.set_app_id(app_id)

    def on_open_steamdb_depot(self, depot_id: str):
        """Switch to browser tab and load depot_id."""
        self.tabs.setCurrentWidget(self.browser_tab)
        self.browser_tab.set_depot_id(depot_id)

    def on_parse_depots_steamdb(self, app_id: str):
        """Switch to browser tab and automatically run DepotsParsingTask."""
        from src.steamdb_tasks import DepotsParsingTask
        self.tabs.setCurrentWidget(self.browser_tab)
        self.browser_tab.run_task(DepotsParsingTask, app_id)

    def on_scrape_manifests_steamdb(self, depot_ids: list):
        """Switch to browser tab and automatically run ManifestsParsingTask for a queue of depots."""
        from src.steamdb_tasks import ManifestsParsingTask
        self.tabs.setCurrentWidget(self.browser_tab)
        self.browser_tab.run_task_queue(ManifestsParsingTask, depot_ids)

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
    app.setApplicationName("SteamDepoter2")
    app.setOrganizationName("SteamDepoter")

    from src.settings import settings
    from src import manifest_filters

    settings.migrate_library_hide_patterns_from_qsettings()
    manifest_filters.init_from_app_settings(settings)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
