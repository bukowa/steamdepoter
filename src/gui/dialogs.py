"""Dialog widgets for creating/editing entities."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget, QWidget, QFormLayout
)
from pydantic import BaseModel, ValidationError

from src.db.validation import GameCreate, DepotCreate
from src.errors.exceptions_handler import show_validation_error
from src.settings import settings


class SettingsDialog(QDialog):
    """Dialog for managing application settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(500, 400)
        self.fields = {} # {(group, key): QLineEdit}
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        
        self.tab_widget = QTabWidget()
        all_settings = settings.get_all_settings()
        
        # Sort groups: globals first, then alphabetically
        groups = sorted(all_settings.keys())
        if "globals" in groups:
            groups.remove("globals")
            groups.insert(0, "globals")
            
        for group in groups:
            tab = QWidget()
            tab_layout = QFormLayout(tab)
            
            group_settings = all_settings[group]
            for key, value in group_settings.items():
                input_field = QLineEdit(str(value))
                if "password" in key.lower():
                    input_field.setEchoMode(QLineEdit.EchoMode.Password)
                
                self.fields[(group, key)] = input_field
                tab_layout.addRow(QLabel(f"{key}:"), input_field)
            
            self.tab_widget.addTab(tab, group.capitalize())
            
        layout.addWidget(self.tab_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

    def accept(self) -> None:
        """Save settings before closing."""
        for (group, key), field in self.fields.items():
            val = field.text()
            settings.set(group, key, val)
        
        super().accept()


class BaseFormDialog(QDialog):
    """Base dialog for form-based input with config-driven fields."""

    def __init__(self, parent=None, title="Dialog", schema: BaseModel = None, fields_config: dict = None):
        """Initialize form dialog.

        Args:
            parent: Parent widget
            title: Dialog title
            schema: Pydantic schema for validation
            fields_config: Dict of {field_name: (label, initial_value, readonly)}
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setGeometry(100, 100, 400, 250)
        self.schema = schema
        self.fields_config = fields_config or {}
        self.fields = {}
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout()

        for field_name, config in self.fields_config.items():
            label, initial = config[0], config[1]
            readonly = config[2] if len(config) > 2 else False

            row = QHBoxLayout()
            row.addWidget(QLabel(label))

            input_field = QLineEdit()
            if initial:
                input_field.setText(initial)
            if readonly:
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
        """Validate using Pydantic schema."""
        if not self.schema:
            return True
        try:
            self.schema(**self.get_data())
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
        fields_config = {
            "app_id": ("App ID:", game.app_id if game else "", bool(game)),
            "name": ("Name:", game.name if game else "", False),
        }
        super().__init__(
            parent,
            title="Edit Game" if game else "Add Game",
            schema=GameCreate,
            fields_config=fields_config
        )


class DepotDialog(BaseFormDialog):
    """Dialog for creating/editing a depot."""

    def __init__(self, parent=None, depot=None, app_ids=None):
        fields_config = {
            "depot_id": ("Depot ID:", depot.depot_id if depot else "", bool(depot)),
            "app_id": ("App ID:", depot.app_id if depot else "", bool(depot)),
            "name": ("Name:", depot.name if depot else "", False),
        }
        super().__init__(
            parent,
            title="Edit Depot" if depot else "Add Depot",
            schema=DepotCreate,
            fields_config=fields_config
        )
        self.app_ids = app_ids or []
