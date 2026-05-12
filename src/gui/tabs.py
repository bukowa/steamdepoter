"""Tab widgets for different views."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem, QMessageBox, QDialog, QMenu
)
from PyQt6.QtCore import Qt
from sqlalchemy.orm import Session

from src.services import GameService, DepotService, ManifestService
from src.db.database import Database
from src.gui.dialogs import GameDialog, DepotDialog
from src.gui.workers import CommandWorker
from src.bins.depotdownloader import DepotDownloader
from src.errors.exceptions_handler import show_error


class BaseTab(QWidget):
    """Base tab with common CRUD operations."""

    def __init__(self, session: Session, console=None, db: Database = None):
        super().__init__()
        self.session = session
        self.console = console
        self.db = db
        self.tree_view = None
        self.init_ui()

    def get_service(self):
        """Return the service instance. Must be overridden by subclass."""
        raise NotImplementedError("Subclass must implement get_service()")

    def refresh_data(self) -> None:
        """Load and display data. Must be overridden by subclass."""
        raise NotImplementedError("Subclass must implement refresh_data()")

    def on_add(self) -> None:
        """Handle add action. Must be overridden by subclass."""
        raise NotImplementedError("Subclass must implement on_add()")

    def on_delete(self) -> None:
        """Handle delete action. Must be overridden by subclass."""
        raise NotImplementedError("Subclass must implement on_delete()")

    def init_ui(self) -> None:
        layout = QVBoxLayout()

        # Toolbar
        toolbar = QHBoxLayout()
        add_btn = self._make_button("Add", self.on_add)
        del_btn = self._make_button("Delete", self.on_delete)
        ref_btn = self._make_button("Refresh", self.refresh_data)

        toolbar.addWidget(add_btn)
        toolbar.addWidget(del_btn)
        toolbar.addWidget(ref_btn)
        toolbar.addStretch()

        self.tree_view = QTreeWidget()
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.on_context_menu)
        
        self.refresh_data()

        layout.addLayout(toolbar)
        layout.addWidget(self.tree_view)
        self.setLayout(layout)

    def on_context_menu(self, point) -> None:
        """Handle context menu. Can be overridden by subclass."""
        pass

    @staticmethod
    def _make_button(label: str, callback) -> QPushButton:
        """Create a button with a callback."""
        btn = QPushButton(label)
        btn.clicked.connect(callback)
        return btn

    def _get_selected_item(self) -> object:
        item = self.tree_view.currentItem()
        if not item:
            QMessageBox.warning(self, "Error", "Please select an item")
            return None

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            QMessageBox.warning(self, "Error", "Invalid selection")
            return None

        return data


class GamesTab(BaseTab):

    def get_service(self):
        return GameService(self.session)

    def refresh_data(self) -> None:
        self.tree_view.clear()
        self.tree_view.setHeaderLabels(["App ID", "Name"])
        
        service = self.get_service()
        games = service.get_all_games()
        
        for game in games:
            game_item = QTreeWidgetItem(self.tree_view)
            game_item.setText(0, str(game.app_id))
            game_item.setText(1, game.name)
            game_item.setData(0, Qt.ItemDataRole.UserRole, game)
            game_item.setText(0, f"📁 {game.app_id}") # Add icon emoji
            
            for depot in game.depots:
                depot_item = QTreeWidgetItem(game_item)
                depot_item.setText(0, str(depot.depot_id))
                depot_item.setText(1, depot.name)
                depot_item.setData(0, Qt.ItemDataRole.UserRole, depot)
                depot_item.setText(0, f"📦 {depot.depot_id}")

        self.tree_view.expandAll()
        for i in range(self.tree_view.columnCount()):
            self.tree_view.resizeColumnToContents(i)

    def on_context_menu(self, point) -> None:
        item = self.tree_view.itemAt(point)
        if not item:
            return

        # Check if it's a game (top-level item)
        if item.parent() is not None:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or not hasattr(data, 'app_id'):
            return

        menu = QMenu(self)
        parse_action = menu.addAction("Parse Manifests (get_depots)")
        parse_action.triggered.connect(lambda: self.on_parse_manifests(data))
        
        menu.exec(self.tree_view.mapToGlobal(point))

    def on_parse_manifests(self, game) -> None:
        if not self.console:
            return

        downloader = DepotDownloader()
        
        def on_finished(output):
            # Use a fresh session for background task to avoid crashes
            if self.db:
                new_session = self.db.get_session()
                try:
                    service = ManifestService(new_session)
                    service.save_manifests(game.app_id, output.manifests)
                    # Use QTimer or similar if we wanted to refresh UI from here, 
                    # but for now let's just log or rely on manual refresh
                except Exception as e:
                    print(f"Failed to save manifests: {e}")
                finally:
                    new_session.close()
            else:
                # Fallback to current session (risky)
                try:
                    service = ManifestService(self.session)
                    service.save_manifests(game.app_id, output.manifests)
                except Exception as e:
                    print(f"Failed to save manifests (shared session): {e}")

        worker = CommandWorker(downloader.get_depots, app_id=int(game.app_id))
        worker.finished.connect(on_finished)
        
        self.console.add_command(worker, f"Get Depots: {game.name}")

    def on_add(self) -> None:
        dialog = GameDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                service = self.get_service()
                service.create_game(props=data)
                self.refresh_data()
                QMessageBox.information(self, "Success", f"Game '{data['name']}' added successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Add Game")

    def on_delete(self) -> None:
        """Delete selected game."""
        game = self._get_selected_item()
        if not game:
            return

        response = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete game '{game.name}' and all its depots?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if response == QMessageBox.StandardButton.Yes:
            try:
                service = self.get_service()
                service.delete_game(game.id)
                self.refresh_data()
                QMessageBox.information(self, "Success", "Game deleted successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Delete Game")


class DepotsTab(BaseTab):

    def get_service(self):
        return DepotService(self.session)

    def refresh_data(self) -> None:
        self.tree_view.clear()
        self.tree_view.setHeaderLabels(["Depot ID", "Name", "App ID"])
        
        service = self.get_service()
        depots = service.get_all_depots()
        
        for depot in depots:
            item = QTreeWidgetItem(self.tree_view)
            item.setText(0, f"📦 {depot.depot_id}")
            item.setText(1, depot.name)
            item.setText(2, str(depot.app_id))
            item.setData(0, Qt.ItemDataRole.UserRole, depot)

        for i in range(self.tree_view.columnCount()):
            self.tree_view.resizeColumnToContents(i)

    def on_add(self) -> None:
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
                service = self.get_service()
                service.create_depot(props=data)
                self.refresh_data()
                QMessageBox.information(self, "Success", f"Depot '{data['name']}' added successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Add Depot")

    def on_delete(self) -> None:
        depot = self._get_selected_item()
        if not depot:
            return

        response = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete depot '{depot.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if response == QMessageBox.StandardButton.Yes:
            try:
                service = self.get_service()
                service.delete_depot(depot.id)
                self.refresh_data()
                QMessageBox.information(self, "Success", "Depot deleted successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Delete Depot")
