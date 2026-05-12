"""Dialog widgets for creating/editing entities."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)
from pydantic import BaseModel, ValidationError

from src.schemas import GameCreate, DepotCreate
from src.exceptions_handler import show_validation_error


class BaseFormDialog(QDialog):
    """Base dialog for form-based input."""

    def __init__(self, parent=None, title="Dialog", readonly_fields=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setGeometry(100, 100, 400, 250)
        self.readonly_fields = readonly_fields or set()
        self.fields = {}
        self.init_ui()

    def get_schema(self) -> type[BaseModel]:
        """Return Pydantic schema class. Must be overridden by subclass."""
        raise NotImplementedError("Subclass must implement get_schema()")

    def get_field_config(self) -> dict:
        """Return {field_name: (label, initial_value)}. Must be overridden by subclass."""
        raise NotImplementedError("Subclass must implement get_field_config()")

    def init_ui(self) -> None:
        layout = QVBoxLayout()

        for field_name, (label, initial) in self.get_field_config().items():
            row = QHBoxLayout()
            row.addWidget(QLabel(label))

            input_field = QLineEdit()
            if initial:
                input_field.setText(initial)
            if field_name in self.readonly_fields:
                input_field.setReadOnly(True)

            self.fields[field_name] = input_field
            row.addWidget(input_field)
            layout.addLayout(row)

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
        """Return form data."""
        return {name: field.text().strip() for name, field in self.fields.items()}

    def validate(self) -> bool:
        """Validate using Pydantic."""
        try:
            self.get_schema()(**self.get_data())
            return True
        except ValidationError as e:
            errors = {error['loc'][0]: error for error in e.errors()}
            show_validation_error(self, errors)
            return False

    def accept(self) -> None:
        """Override accept to validate before closing."""
        if self.validate():
            super().accept()


class GameDialog(BaseFormDialog):
    """Dialog for creating/editing a game."""

    def __init__(self, parent=None, game=None):
        """
        Initialize game dialog.

        Args:
            parent: Parent widget
            game: Existing game object (for editing). None for new game.
        """
        self.game = game
        super().__init__(
            parent,
            title="Edit Game" if game else "Add Game",
            readonly_fields={"app_id"} if game else set()
        )

    def get_schema(self) -> type[BaseModel]:
        return GameCreate

    def get_field_config(self) -> dict:
        return {
            "app_id": ("App ID:", self.game.app_id if self.game else ""),
            "name": ("Name:", self.game.name if self.game else ""),
        }


class DepotDialog(BaseFormDialog):
    """Dialog for creating/editing a depot."""

    def __init__(self, parent=None, depot=None, app_ids=None):
        """
        Initialize depot dialog.

        Args:
            parent: Parent widget
            depot: Existing depot object (for editing). None for new depot.
            app_ids: List of available app IDs for selection
        """
        self.depot = depot
        self.app_ids = app_ids or []
        super().__init__(
            parent,
            title="Edit Depot" if depot else "Add Depot",
            readonly_fields={"depot_id", "app_id"} if depot else set()
        )

    def get_schema(self) -> type[BaseModel]:
        return DepotCreate

    def get_field_config(self) -> dict:
        return {
            "depot_id": ("Depot ID:", self.depot.depot_id if self.depot else ""),
            "app_id": ("App ID:", self.depot.app_id if self.depot else ""),
            "name": ("Name:", self.depot.name if self.depot else ""),
        }
