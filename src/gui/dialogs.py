"""Dialog widgets for creating/editing entities."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt
from pydantic import ValidationError

from src.schemas import GameCreate, DepotCreate
from src.exceptions_handler import show_validation_error


class GameDialog(QDialog):
    """Dialog for creating/editing a game."""

    def __init__(self, parent=None, game=None):
        """
        Initialize game dialog.

        Args:
            parent: Parent widget
            game: Existing game object (for editing). None for new game.
        """
        super().__init__(parent)
        self.game = game
        self.setWindowTitle("Add Game" if not game else "Edit Game")
        self.setModal(True)
        self.setGeometry(100, 100, 400, 200)
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout()

        # App ID field
        app_id_layout = QHBoxLayout()
        app_id_layout.addWidget(QLabel("App ID:"))
        self.app_id_input = QLineEdit()
        if self.game:
            self.app_id_input.setText(self.game.app_id)
            self.app_id_input.setReadOnly(True)  # Can't change ID
        app_id_layout.addWidget(self.app_id_input)
        layout.addLayout(app_id_layout)

        # Name field
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        if self.game:
            self.name_input.setText(self.game.name)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def get_data(self) -> dict:
        """Return dialog data as dictionary."""
        return {
            "app_id": self.app_id_input.text().strip(),
            "name": self.name_input.text().strip(),
        }

    def validate(self) -> bool:
        """Validate input fields using Pydantic."""
        data = self.get_data()

        try:
            GameCreate(**data)
            return True
        except ValidationError as e:
            # Convert Pydantic errors to a more usable format
            errors = {error['loc'][0]: error for error in e.errors()}
            show_validation_error(self, errors)
            return False


    def accept(self) -> None:
        """Override accept to validate before closing."""
        if self.validate():
            super().accept()


class DepotDialog(QDialog):
    """Dialog for creating/editing a depot."""

    def __init__(self, parent=None, depot=None, app_ids=None):
        """
        Initialize depot dialog.

        Args:
            parent: Parent widget
            depot: Existing depot object (for editing). None for new depot.
            app_ids: List of available app IDs for selection
        """
        super().__init__(parent)
        self.depot = depot
        self.app_ids = app_ids or []
        self.setWindowTitle("Add Depot" if not depot else "Edit Depot")
        self.setModal(True)
        self.setGeometry(100, 100, 400, 250)
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout()

        # Depot ID field
        depot_id_layout = QHBoxLayout()
        depot_id_layout.addWidget(QLabel("Depot ID:"))
        self.depot_id_input = QLineEdit()
        if self.depot:
            self.depot_id_input.setText(self.depot.depot_id)
            self.depot_id_input.setReadOnly(True)
        depot_id_layout.addWidget(self.depot_id_input)
        layout.addLayout(depot_id_layout)

        # App ID field
        app_id_layout = QHBoxLayout()
        app_id_layout.addWidget(QLabel("App ID:"))
        self.app_id_input = QLineEdit()
        if self.depot:
            self.app_id_input.setText(self.depot.app_id)
            self.app_id_input.setReadOnly(True)
        app_id_layout.addWidget(self.app_id_input)
        layout.addLayout(app_id_layout)

        # Name field
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        if self.depot:
            self.name_input.setText(self.depot.name)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def get_data(self) -> dict:
        """Return dialog data as dictionary."""
        return {
            "depot_id": self.depot_id_input.text().strip(),
            "app_id": self.app_id_input.text().strip(),
            "name": self.name_input.text().strip(),
        }

    def validate(self) -> bool:
        """Validate input fields using Pydantic."""
        data = self.get_data()

        try:
            DepotCreate(**data)
            return True
        except ValidationError as e:
            # Convert Pydantic errors to a more usable format
            errors = {error['loc'][0]: error for error in e.errors()}
            show_validation_error(self, errors)
            return False


    def accept(self) -> None:
        """Override accept to validate before closing."""
        if self.validate():
            super().accept()

