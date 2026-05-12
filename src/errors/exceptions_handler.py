"""Centralized exception handling utilities for the application."""
from typing import Optional
from PyQt6.QtWidgets import QMessageBox, QWidget

from src.errors.errors import SteamDepoterError



def show_error(parent: Optional[QWidget], exception: Exception, title: str = "Error") -> None:
    """Show an error dialog for an exception.

    Args:
        parent: The parent widget for the message box
        exception: The exception that occurred
        title: Title for the error dialog
    """
    if isinstance(exception, SteamDepoterError):
        message = exception.get_user_message()
    else:
        message = str(exception) or "An unknown error occurred"

    QMessageBox.warning(parent, title, message)


def show_validation_error(parent: Optional[QWidget], errors: dict) -> None:
    """Show a validation error dialog with structured errors.

    Args:
        parent: The parent widget for the message box
        errors: Dictionary of field errors from Pydantic
    """
    error_lines = [f"{field}: {error['msg']}" for field, error in errors.items()]
    message = "\n".join(error_lines)
    QMessageBox.warning(parent, "Validation Error", message)
