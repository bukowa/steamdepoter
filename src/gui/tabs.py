"""Tab widgets for different views."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeView, QMessageBox, QDialog, QMenu
)
from PyQt6.QtCore import Qt
from sqlalchemy.orm import Session

from src.services import GameService, DepotService, ManifestService
from src.gui.models import SQLAlchemyTreeModel
from src.gui.dialogs import GameDialog, DepotDialog
from src.gui.workers import CommandWorker
from src.bins.depotdownloader import DepotDownloader
from src.errors.exceptions_handler import show_error


class BaseTab(QWidget):
    """Base tab with common CRUD operations."""

    def __init__(self, session: Session, console=None):
        super().__init__()
        self.session = session
        self.console = console
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

        self.tree_view = QTreeView()
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
        current_index = self.tree_view.currentIndex()
        if not current_index.isValid():
            QMessageBox.warning(self, "Error", "Please select an item")
            return None

        item = current_index.internalPointer()
        if item.data is None:
            QMessageBox.warning(self, "Error", "Invalid selection")
            return None

        return item.data


class GamesTab(BaseTab):

    def get_service(self):
        return GameService(self.session)

    def refresh_data(self) -> None:
        service = self.get_service()
        games = service.get_all_games()
        model = SQLAlchemyTreeModel(
            games,
            columns=["app_id", "name"],
            relationship_attr="depots"
        )
        self.tree_view.setModel(model)
        self.tree_view.expandAll()

    def on_context_menu(self, point) -> None:
        index = self.tree_view.indexAt(point)
        if not index.isValid():
            return

        item = index.internalPointer()
        if not item or not hasattr(item.data, 'app_id'):
            return

        menu = QMenu(self)
        parse_action = menu.addAction("Parse Manifests (get_depots)")
        parse_action.triggered.connect(lambda: self.on_parse_manifests(item.data))
        
        menu.exec(self.tree_view.mapToGlobal(point))

    def on_parse_manifests(self, game) -> None:
        if not self.console:
            return

        downloader = DepotDownloader()
        
        def on_finished(output):
            try:
                # Note: In a real app, we might need a thread-safe way to use the session
                service = ManifestService(self.session)
                service.save_manifests(game.app_id, output.manifests)
                # We could refresh DepotsTab here if we had a reference to it
            except Exception as e:
                print(f"Failed to save manifests: {e}")

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
        service = self.get_service()
        depots = service.get_all_depots()
        model = SQLAlchemyTreeModel(
            depots,
            columns=["depot_id", "name", "app_id"],
            relationship_attr=None  # TODO: Add manifests relationship
        )
        self.tree_view.setModel(model)
        self.tree_view.expandAll()

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
