"""Tab widgets for different views."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeView, QMessageBox, QDialog
)
from sqlalchemy.orm import Session

from src.services import GameService, DepotService
from src.gui.models import SQLAlchemyTreeModel
from src.gui.dialogs import GameDialog, DepotDialog
from src.exceptions_handler import show_error


class BaseTab(QWidget):
    """Base tab with common CRUD operations."""

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
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
        self.refresh_data()

        layout.addLayout(toolbar)
        layout.addWidget(self.tree_view)
        self.setLayout(layout)

    @staticmethod
    def _make_button(label: str, callback) -> QPushButton:
        """Create a button with a callback."""
        btn = QPushButton(label)
        btn.clicked.connect(callback)
        return btn

    def _get_selected_item(self):
        """Get selected item from tree view."""
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
    """Tab for displaying games with expandable depots."""

    def get_service(self):
        return GameService(self.session)

    def refresh_data(self) -> None:
        """Load games from database and update tree view."""
        service = self.get_service()
        games = service.get_all_games()
        model = SQLAlchemyTreeModel(
            games,
            columns=["app_id", "name"],
            relationship_attr="depots"
        )
        self.tree_view.setModel(model)
        self.tree_view.expandAll()

    def on_add(self) -> None:
        """Add a new game."""
        dialog = GameDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                service = self.get_service()
                service.create_game(data["app_id"], data["name"])
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
    """Tab for displaying depots with expandable manifests."""

    def get_service(self):
        return DepotService(self.session)

    def refresh_data(self) -> None:
        """Load depots from database and update tree view."""
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
        """Add a new depot."""
        # Get list of available app IDs
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
                service.create_depot(data["depot_id"], data["app_id"], data["name"])
                self.refresh_data()
                QMessageBox.information(self, "Success", f"Depot '{data['name']}' added successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Add Depot")

    def on_delete(self) -> None:
        """Delete selected depot."""
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

