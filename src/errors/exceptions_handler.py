"""Centralized exception handling utilities for the application."""
from typing import Optional
from PyQt6.QtWidgets import QMessageBox, QWidget, QDialog, QVBoxLayout, QTextEdit, QLabel, QDialogButtonBox
from PyQt6.QtCore import Qt

from src.errors.errors import SteamDepoterError



class CopyableErrorDialog(QDialog):
    """A dialog that displays an error message in a selectable text area."""
    def __init__(self, parent: Optional[QWidget], title: str, message: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        
        layout = QVBoxLayout(self)
        
        msg_label = QLabel("Details (selectable for copy):")
        layout.addWidget(msg_label)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(message)
        # Use a monospace font for better readability of technical errors
        self.text_edit.setStyleSheet("font-family: 'Consolas', 'Monaco', 'Courier New', monospace;")
        layout.addWidget(self.text_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

def show_error(parent: Optional[QWidget], exception: Exception, title: str = "Error") -> None:
    """Show an error dialog for an exception with selectable text."""
    if isinstance(exception, SteamDepoterError):
        message = exception.get_user_message()
    else:
        message = str(exception) or "An unknown error occurred"

    dialog = CopyableErrorDialog(parent, title, message)
    dialog.exec()


def show_validation_error(parent: Optional[QWidget], errors: dict) -> None:
    """Show a validation error dialog with structured, selectable errors."""
    error_lines = [f"Field: {field}\nError: {error['msg']}\n" for field, error in errors.items()]
    message = "\n".join(error_lines)
    
    dialog = CopyableErrorDialog(parent, "Validation Error", message)
    dialog.exec()
