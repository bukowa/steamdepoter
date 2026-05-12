"""Tab widgets for different views."""
import random
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem, 
    QMessageBox, QDialog, QMenu, QTabWidget, QLineEdit, QLabel, QTextEdit, 
    QListWidget, QListWidgetItem, QSplitter, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from sqlalchemy.orm import Session

from src.settings import Configurable
from src.services import GameService, DepotService, ManifestService
from src.db.database import Database
from src.db import Game, Depot, Manifest
from src.gui.dialogs import GameDialog, DepotDialog
from src.gui.workers import CommandWorker
from src.bins.depotdownloader import DepotDownloader
from src.errors.exceptions_handler import show_error
from src.steamdb_tasks import DepotsParsingTask, ManifestsParsingTask
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

class LibraryTab(QWidget):
    """Unified Library Tab displaying Games, Depots, Manifests, and Files."""
    
    data_changed = pyqtSignal()
    open_steamdb = pyqtSignal(str)
    parse_depots_steamdb = pyqtSignal(str)
    scrape_manifests_steamdb = pyqtSignal(list)

    def __init__(self, session: Session, console=None, db: Database = None):
        super().__init__()
        self.session = session
        self.console = console
        self.db = db
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout()

        # Toolbar
        toolbar = QHBoxLayout()
        add_game_btn = self._make_button("Add Game", self.on_add_game)
        add_depot_btn = self._make_button("Add Depot", self.on_add_depot)
        del_btn = self._make_button("Delete Selected", self.on_delete)
        ref_btn = self._make_button("Refresh", self._manual_refresh)

        toolbar.addWidget(add_game_btn)
        toolbar.addWidget(add_depot_btn)
        toolbar.addWidget(del_btn)
        toolbar.addWidget(ref_btn)
        toolbar.addStretch()

        from src.gui.components import EntityTreeWidget
        self.tree_view = EntityTreeWidget(self.session)
        
        # Connect signals
        self.tree_view.open_steamdb_requested.connect(self.open_steamdb.emit)
        self.tree_view.parse_depots_requested.connect(self.parse_depots_steamdb.emit)
        self.tree_view.scrape_manifests_requested.connect(self.scrape_manifests_steamdb.emit)
        self.tree_view.download_manifest_requested.connect(self.on_download_manifests)

        self.refresh_data()

        layout.addLayout(toolbar)
        layout.addWidget(self.tree_view)
        self.setLayout(layout)

    @staticmethod
    def _make_button(label: str, callback) -> QPushButton:
        btn = QPushButton(label)
        btn.clicked.connect(callback)
        return btn

    def refresh_data(self) -> None:
        self.tree_view.load_games()

    def _manual_refresh(self) -> None:
        self.session.expire_all()
        self.refresh_data()

    def on_add_game(self) -> None:
        dialog = GameDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                service = GameService(self.session)
                service.create_game(props=data)
                self.data_changed.emit()
                self._manual_refresh()
                QMessageBox.information(self, "Success", f"Game '{data['name']}' added successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Add Game")

    def on_add_depot(self) -> None:
        try:
            game_service = GameService(self.session)
            games = game_service.get_all_games()
        except Exception as e:
            show_error(self, e, "Failed to Load Games")
            return

        app_ids = [game.app_id for game in games]

        if not app_ids:
            QMessageBox.warning(self, "Error", "No games exist. Please add a game first!")
            return

        dialog = DepotDialog(self, app_ids=app_ids)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                service = DepotService(self.session)
                service.create_depot(props=data)
                self.data_changed.emit()
                self._manual_refresh()
                QMessageBox.information(self, "Success", f"Depot '{data['name']}' added successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Add Depot")

    def on_delete(self) -> None:
        selected_data = self.tree_view._get_selected_items()
        if not selected_data:
            QMessageBox.warning(self, "Error", "Please select items to delete.")
            return

        games = [item for item in selected_data if isinstance(item, Game)]
        depots = [item for item in selected_data if isinstance(item, Depot)]
        manifests = [item for item in selected_data if isinstance(item, Manifest)]
        
        msg_parts = []
        if games: msg_parts.append(f"{len(games)} game(s)")
        if depots: msg_parts.append(f"{len(depots)} depot(s)")
        if manifests: msg_parts.append(f"{len(manifests)} manifest(s)")
        
        if not msg_parts:
            return

        msg = "Delete " + " and ".join(msg_parts) + "?"
        if games:
            msg += "\nWarning: Deleting a game will delete all its depots and manifests!"

        response = QMessageBox.question(
            self,
            "Confirm Delete",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if response == QMessageBox.StandardButton.Yes:
            try:
                if games:
                    GameService(self.session).delete_games([g.id for g in games])
                if depots:
                    # Filter out depots whose games are already being deleted to avoid errors
                    depot_ids = [d.id for d in depots if not any(g.app_id == d.app_id for g in games)]
                    if depot_ids:
                        DepotService(self.session).delete_depots(depot_ids)
                if manifests:
                    manifest_ids = [m.id for m in manifests]
                    ManifestService(self.session).delete_manifests(manifest_ids)
                
                self.data_changed.emit()
                self._manual_refresh()
                QMessageBox.information(self, "Success", "Items deleted successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Delete Items")

    def on_download_manifests(self, manifests: list) -> None:
        if not self.console:
            return

        downloader = DepotDownloader()
        
        targets_by_app = {}
        for m in manifests:
            depot = self.session.query(Depot).filter(Depot.depot_id == m.depot_id).first()
            if not depot:
                QMessageBox.warning(self, "Error", f"Could not find depot for manifest {m.manifest_id}")
                continue
            
            app_id = int(depot.app_id)
            if app_id not in targets_by_app:
                targets_by_app[app_id] = []
            
            targets_by_app[app_id].append(m)

        for app_id, app_manifests in targets_by_app.items():
            targets = [(int(m.depot_id), int(m.manifest_id)) for m in app_manifests]
            
            def make_on_finished(man_list):
                def on_finished(output):
                    if self.db:
                        new_session = self.db.get_session()
                        try:
                            service = ManifestService(new_session)
                            for man in man_list:
                                if output.manifests and int(man.manifest_id) in output.manifests:
                                    parsed_manifest = output.manifests[int(man.manifest_id)]
                                    service.save_downloaded_manifest_files(str(man.manifest_id), parsed_manifest.files)
                                    service.mark_files_parsed(str(man.manifest_id))
                            self.data_changed.emit()
                        except Exception as e:
                            print(f"Failed to process manifest files: {e}")
                        finally:
                            new_session.close()
                return on_finished

            worker = CommandWorker(downloader.get_manifest_data, app_id=app_id, targets=targets)
            worker.finished.connect(make_on_finished(app_manifests))
            
            self.console.add_command(worker, f"Download {len(targets)} Manifest(s) for App {app_id}")


class BrowserTab(QWidget):
    """Browser tab for Steam and SteamDB with a sidebar for parsing tasks."""

    data_changed = pyqtSignal()
    task_queue_finished = pyqtSignal()

    def __init__(self, session: Session, console=None, db: Database = None):
        super().__init__()
        self.session = session
        self.console = console
        self.db = db
        self.current_app_id = None
        self.cancel_requested = False
        self.tasks = [
            DepotsParsingTask,
            ManifestsParsingTask,
        ]
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # URL bar
        url_layout = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Enter URL or App ID...")
        self.url_edit.returnPressed.connect(self.load_url)
        url_layout.addWidget(QLabel("URL:"))
        url_layout.addWidget(self.url_edit)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self.load_url)
        url_layout.addWidget(load_btn)

        steam_btn = QPushButton("Steam Login")
        steam_btn.clicked.connect(self.load_steam)
        url_layout.addWidget(steam_btn)

        layout.addLayout(url_layout)

        # Main splitter for Sidebar and Browser
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sidebar for Tasks
        self.sidebar = QWidget()
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.addWidget(QLabel("<b>SteamDB Tasks</b>"))
        
        self.task_list = QListWidget()
        for task_cls in self.tasks:
            item = QListWidgetItem(task_cls.name)
            item.setToolTip(task_cls.description)
            item.setData(Qt.ItemDataRole.UserRole, task_cls)
            self.task_list.addItem(item)
        
        self.task_list.itemDoubleClicked.connect(self.run_selected_task)
        sidebar_layout.addWidget(self.task_list)

        run_task_btn = QPushButton("Run Task")
        run_task_btn.clicked.connect(self.run_selected_task)
        sidebar_layout.addWidget(run_task_btn)

        cancel_task_btn = QPushButton("Cancel Running Tasks")
        cancel_task_btn.clicked.connect(self.cancel_tasks)
        sidebar_layout.addWidget(cancel_task_btn)
        
        sidebar_layout.addStretch()

        # Web view
        import os
        storage_path = os.path.abspath(os.path.join("data", "browser_storage"))
        os.makedirs(storage_path, exist_ok=True)

        self.profile = QWebEngineProfile("SteamDepoter", self)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setPersistentStoragePath(storage_path)
        self.profile.setCachePath(os.path.join(storage_path, "cache"))
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        
        self.web_view = QWebEngineView()
        self.web_page = QWebEnginePage(self.profile, self.web_view)
        self.web_view.setPage(self.web_page)
        
        # Add components to splitter
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.web_view)
        self.splitter.setStretchFactor(1, 4) # Browser takes more space

        layout.addWidget(self.splitter)
        self.setLayout(layout)

    def set_app_id(self, app_id: str):
        """Programmatically navigate to a specific App ID's depots page."""
        self.current_app_id = app_id
        url = f"https://steamdb.info/app/{app_id}/depots/"
        self.url_edit.setText(url)
        self.web_view.load(QUrl(url))

    def load_url(self):
        url = self.url_edit.text().strip()
        if not url:
            return
            
        if url.isdigit():
            self.set_app_id(url)
            return

        if not url.startswith("http"):
            url = "https://" + url
        self.web_view.load(QUrl(url))

    def load_steam(self):
        url = "https://store.steampowered.com/login/"
        self.url_edit.setText(url)
        self.web_view.load(QUrl(url))

    def cancel_tasks(self):
        self.cancel_requested = True
        if self.console:
            self.console.log_message("System", "Cancellation requested. Tasks will stop before processing the next item.")

    def run_selected_task(self):
        item = self.task_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Error", "Please select a task from the sidebar.")
            return

        task_cls = item.data(Qt.ItemDataRole.UserRole)
        self.run_task(task_cls)

    def run_task(self, task_cls, target_id=None):
        """Run a specific task class, determining target_id from the URL if not provided."""
        if not target_id:
            url = self.web_view.url().toString()
            import re
            
            if task_cls.target_type == "app":
                match = re.search(r"/app/(\d+)", url)
                if match:
                    target_id = match.group(1)
            elif task_cls.target_type == "depot":
                match = re.search(r"/depot/(\d+)", url)
                if match:
                    target_id = match.group(1)
            
        if not target_id:
            QMessageBox.warning(self, "Error", f"Could not determine {task_cls.target_type.upper()} ID from URL or arguments.")
            return

        task = task_cls(self.web_page, str(target_id))

        def on_task_finished(result):
            if result in ["RETRY_REQUIRED", "RATE_LIMITED", None]:
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Icon.Warning)
                
                if result == "RATE_LIMITED":
                    msg_box.setWindowTitle("Rate Limited")
                    msg_box.setText("You have been temporarily rate limited by SteamDB.")
                    msg_box.setInformativeText("It is highly recommended to stop for at least an hour to avoid a permanent ban. Continue at your own risk.")
                else:
                    msg_box.setWindowTitle("Action Required")
                    msg_box.setText("The page failed to load or parse correctly (likely Cloudflare or a block).")
                    msg_box.setInformativeText("Please check the browser tab, solve any challenges, and click 'Continue' to retry.")
                
                continue_btn = msg_box.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
                cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                
                msg_box.exec()
                if msg_box.clickedButton() == continue_btn:
                    if self.console:
                        self.console.log_message(f"{task_cls.name} Task", f"Retrying {target_id}...")
                    self.run_task(task_cls, target_id)
                else:
                    if self.console:
                        self.console.log_message(f"{task_cls.name} Task", "Task cancelled by user.")
                return

            try:
                msg = task.save_result(self.session, result)
                self.data_changed.emit()
                self.task_queue_finished.emit()
                QMessageBox.information(self, "Success", msg)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to process task result: {str(e)}")

        task.run(on_task_finished)

    def run_task_queue(self, task_cls, target_ids: list):
        """Run a task on a list of targets sequentially with a delay to avoid rate limiting."""
        from PyQt6.QtCore import QTimer

        if not target_ids:
            return

        def process_next():
            if self.cancel_requested:
                if self.console:
                    self.console.log_message(f"{task_cls.name} Queue", "Queue cancelled by user.")
                self.cancel_requested = False
                self.task_queue_finished.emit()
                return

            if not target_ids:
                if self.console:
                    self.console.log_message(f"{task_cls.name} Queue", f"Queue finished processing all targets.")
                self.task_queue_finished.emit()
                QMessageBox.information(self, "Queue Finished", f"Finished processing all targets for {task_cls.name}")
                return

            target_id = target_ids.pop(0)
            if self.console:
                self.console.log_message(f"{task_cls.name} Queue", f"Started processing target ID: {target_id}...")

            task = task_cls(self.web_page, str(target_id))

            def on_task_finished(result):
                if result in ["RETRY_REQUIRED", "RATE_LIMITED", None]:
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Icon.Warning)
                    
                    if result == "RATE_LIMITED":
                        msg_box.setWindowTitle("Rate Limited")
                        msg_box.setText("You have been temporarily rate limited by SteamDB.")
                        msg_box.setInformativeText("It is highly recommended to stop for at least an hour. Continuing immediately will likely fail again.")
                    else:
                        msg_box.setWindowTitle("Action Required")
                        msg_box.setText("The page failed to load or parse correctly (likely Cloudflare or a block).")
                        msg_box.setInformativeText("Please check the browser tab, solve any challenges, and click 'Continue' to resume.")
                    
                    continue_btn = msg_box.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
                    stop_btn = msg_box.addButton("Stop Queue", QMessageBox.ButtonRole.RejectRole)
                    
                    msg_box.exec()
                    if msg_box.clickedButton() == continue_btn:
                        if self.console:
                            self.console.log_message(f"{task_cls.name} Queue", f"Retrying {target_id}...")
                        target_ids.insert(0, target_id)
                        QTimer.singleShot(1000, process_next)
                    else:
                        if self.console:
                            self.console.log_message(f"{task_cls.name} Queue", "Queue cancelled by user.")
                    return

                try:
                    # result is guaranteed not to be None here due to the check above
                    msg = task.save_result(self.session, result)
                    
                    # Mark depot as parsed if it's ManifestsParsingTask
                    from src.steamdb_tasks import ManifestsParsingTask
                    if task_cls == ManifestsParsingTask:
                        from src.services import DepotService
                        depot_service = DepotService(self.session)
                        depot_service.mark_manifests_parsed(str(target_id))
                            
                    self.data_changed.emit()
                    if self.console:
                        self.console.log_message(f"{task_cls.name} Queue", f"Success for {target_id}: {msg}")
                except Exception as e:
                    if self.console:
                        self.console.log_message(f"{task_cls.name} Queue", f"Error for {target_id}: {e}")

                if target_ids:
                    delay = random.randint(7000, 15000)
                    if self.console:
                        self.console.log_message(f"{task_cls.name} Queue", f"Waiting {delay/1000:.1f} seconds before next target...")
                    QTimer.singleShot(delay, process_next)
                else:
                    process_next()

            task.run(on_task_finished)

        # Start the queue immediately (the first one is instant!)
        if self.console:
            self.console.log_message(f"{task_cls.name} Queue", f"Initializing queue with {len(target_ids)} targets. First task will start immediately.")
        process_next()

    def _extract_app_id_from_url(self) -> str:
        url = self.web_view.url().toString()
        import re
        match = re.search(r"/app/(\d+)", url)
        return match.group(1) if match else None

    def refresh_data(self):
        pass

