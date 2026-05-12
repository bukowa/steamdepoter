"""Custom exceptions for SteamDepoter2."""


class SteamDepoterError(Exception):
    """Base exception for all SteamDepoter errors."""

    category: str = "error"

    def serialize(self) -> dict:
        """Serialize exception to a structured format.

        Returns:
            dict: Dictionary with 'type' and 'message' keys for UI display.
        """
        return {
            "type": self.__class__.__name__,
            "message": str(self),
            "category": self.category,
        }

    def get_user_message(self) -> str:
        """Get a user-friendly error message.

        Returns:
            str: Message suitable for displaying in UI.
        """
        return str(self)


class DatabaseError(SteamDepoterError):
    """Database operation failed."""

    category = "database_error"


class DuplicateError(DatabaseError):
    """Duplicate entry error."""

    category = "duplicate_error"


class NotFoundError(DatabaseError):
    """Entity not found error."""

    category = "not_found_error"


class ForeignKeyError(DatabaseError):
    """Foreign key constraint error."""

    category = "foreign_key_error"
