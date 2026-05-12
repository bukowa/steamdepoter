"""Tab widgets for different views."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeView
from sqlalchemy.orm import Session

from src.db import Game, Depot
from src.gui.models import SQLAlchemyTreeModel


class GamesTab(QWidget):
    """Tab for displaying games with expandable depots."""

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
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
        games = self.session.query(Game).all()
        model = SQLAlchemyTreeModel(
            games,
            columns=["app_id", "name"],
            relationship_attr="depots"
        )
        self.tree_view.setModel(model)
        self.tree_view.expandAll()

    def on_add_game(self) -> None:
        """Add a new game."""
        # TODO: Open dialog to create game
        pass

    def on_delete_game(self) -> None:
        """Delete selected game."""
        # TODO: Delete logic
        pass


class DepotsTab(QWidget):
    """Tab for displaying depots with expandable manifests."""

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
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
        depots = self.session.query(Depot).all()
        model = SQLAlchemyTreeModel(
            depots,
            columns=["depot_id", "name", "app_id"],
            relationship_attr=None  # TODO: Add manifests relationship
        )
        self.tree_view.setModel(model)
        self.tree_view.expandAll()

    def on_add_depot(self) -> None:
        """Add a new depot."""
        # TODO: Open dialog to create depot
        pass

    def on_delete_depot(self) -> None:
        """Delete selected depot."""
        # TODO: Delete logic
        pass


