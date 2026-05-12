"""Centralized exception handling utilities for the application."""
from typing import Callable, Optional, Any, TypeVar
from functools import wraps
from PyQt6.QtWidgets import QMessageBox, QWidget

from src.errors import SteamDepoterError

T = TypeVar("T")


def handle_exception(parent: Optional[QWidget] = None, title: str = "Error") -> Callable:
    """Decorator for handling exceptions in GUI operations.

    Usage:
        @handle_exception(parent=self, title="Operation Failed")
        def my_operation(self):
            # code that might raise SteamDepoterError
            pass

    Args:
        parent: The parent widget for the message box
        title: Title for the error dialog

    Returns:
        Decorator function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Optional[T]:
            try:
                return func(*args, **kwargs)
            except SteamDepoterError as e:
                error_info = e.serialize()
                message = e.get_user_message()
                QMessageBox.warning(
                    parent,
                    title,
                    message,
                )
                return None
            except Exception as e:
                # Catch unexpected exceptions
                QMessageBox.critical(
                    parent,
                    "Unexpected Error",
                    f"An unexpected error occurred: {str(e)}",
                )
                return None
        return wrapper
    return decorator


def show_error(parent: Optional[QWidget], exception: Exception, title: str = "Error") -> None:
    """Show error dialog for an exception.

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
    """Show validation error dialog with structured errors.

    Args:
        parent: The parent widget for the message box
        errors: Dictionary of field errors from Pydantic
    """
    error_lines = [f"{field}: {error['msg']}" for field, error in errors.items()]
    message = "\n".join(error_lines)
    QMessageBox.warning(parent, "Validation Error", message)

