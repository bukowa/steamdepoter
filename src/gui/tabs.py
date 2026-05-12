"""Tab widgets for different views."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeView, QMessageBox, QDialog
)
from sqlalchemy.orm import Session

from src.services import GameService, DepotService
from src.gui.models import SQLAlchemyTreeModel
from src.gui.dialogs import GameDialog, DepotDialog
from src.exceptions_handler import show_error


class GamesTab(QWidget):
    """Tab for displaying games with expandable depots."""

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self.game_service = GameService(session)
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout()

        # Toolbar
        toolbar_layout = QHBoxLayout()
        add_btn = QPushButton("Add Game")
        delete_btn = QPushButton("Delete Game")
        refresh_btn = QPushButton("Refresh")

        toolbar_layout.addWidget(add_btn)
        toolbar_layout.addWidget(delete_btn)
        toolbar_layout.addWidget(refresh_btn)
        toolbar_layout.addStretch()

        # Tree view
        self.tree_view = QTreeView()
        self.refresh_data()

        # Connections
        refresh_btn.clicked.connect(self.refresh_data)
        add_btn.clicked.connect(self.on_add_game)
        delete_btn.clicked.connect(self.on_delete_game)

        layout.addLayout(toolbar_layout)
        layout.addWidget(self.tree_view)
        self.setLayout(layout)

    def refresh_data(self) -> None:
        """Load games from database and update tree view."""
        games = self.game_service.get_all_games()
        model = SQLAlchemyTreeModel(
            games,
            columns=["app_id", "name"],
            relationship_attr="depots"
        )
        self.tree_view.setModel(model)
        self.tree_view.expandAll()

    def on_add_game(self) -> None:
        """Add a new game."""
        dialog = GameDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                self.game_service.create_game(data["app_id"], data["name"])
                self.refresh_data()
                QMessageBox.information(self, "Success", f"Game '{data['name']}' added successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Add Game")

    def on_delete_game(self) -> None:
        """Delete selected game."""
        current_index = self.tree_view.currentIndex()
        if not current_index.isValid():
            QMessageBox.warning(self, "Error", "Please select a game to delete")
            return

        item = current_index.internalPointer()
        if item.data is None:
            QMessageBox.warning(self, "Error", "Invalid selection")
            return

        game = item.data
        response = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete game '{game.name}' and all its depots?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if response == QMessageBox.StandardButton.Yes:
            try:
                self.game_service.delete_game(game.id)
                self.refresh_data()
                QMessageBox.information(self, "Success", "Game deleted successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Delete Game")


class DepotsTab(QWidget):
    """Tab for displaying depots with expandable manifests."""

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self.game_service = GameService(session)
        self.depot_service = DepotService(session)
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout()

        # Toolbar
        toolbar_layout = QHBoxLayout()
        add_btn = QPushButton("Add Depot")
        delete_btn = QPushButton("Delete Depot")
        refresh_btn = QPushButton("Refresh")

        toolbar_layout.addWidget(add_btn)
        toolbar_layout.addWidget(delete_btn)
        toolbar_layout.addWidget(refresh_btn)
        toolbar_layout.addStretch()

        # Tree view
        self.tree_view = QTreeView()
        self.refresh_data()

        # Connections
        refresh_btn.clicked.connect(self.refresh_data)
        add_btn.clicked.connect(self.on_add_depot)
        delete_btn.clicked.connect(self.on_delete_depot)

        layout.addLayout(toolbar_layout)
        layout.addWidget(self.tree_view)
        self.setLayout(layout)

    def refresh_data(self) -> None:
        """Load depots from database and update tree view."""
        depots = self.depot_service.get_all_depots()
        model = SQLAlchemyTreeModel(
            depots,
            columns=["depot_id", "name", "app_id"],
            relationship_attr=None  # TODO: Add manifests relationship
        )
        self.tree_view.setModel(model)
        self.tree_view.expandAll()

    def on_add_depot(self) -> None:
        """Add a new depot."""
        # Get list of available app IDs
        try:
            games = self.game_service.get_all_games()
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
                self.depot_service.create_depot(data["depot_id"], data["app_id"], data["name"])
                self.refresh_data()
                QMessageBox.information(self, "Success", f"Depot '{data['name']}' added successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Add Depot")

    def on_delete_depot(self) -> None:
        """Delete selected depot."""
        current_index = self.tree_view.currentIndex()
        if not current_index.isValid():
            QMessageBox.warning(self, "Error", "Please select a depot to delete")
            return

        item = current_index.internalPointer()
        if item.data is None:
            QMessageBox.warning(self, "Error", "Invalid selection")
            return

        depot = item.data
        response = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete depot '{depot.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if response == QMessageBox.StandardButton.Yes:
            try:
                self.depot_service.delete_depot(depot.id)
                self.refresh_data()
                QMessageBox.information(self, "Success", "Depot deleted successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Delete Depot")


