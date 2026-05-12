"""Custom exceptions for SteamDepoter2."""


class SteamDepoterError(Exception):
    """Base exception for all SteamDepoter errors."""

    def serialize(self) -> dict:
        """Serialize exception to a structured format.

        Returns:
            dict: Dictionary with 'type' and 'message' keys for UI display.
        """
        return {
            "type": self.__class__.__name__,
            "message": str(self),
            "category": "error",
        }

    def get_user_message(self) -> str:
        """Get a user-friendly error message.

        Returns:
            str: Message suitable for displaying in UI.
        """
        return str(self)


class DatabaseError(SteamDepoterError):
    """Database operation failed."""

    def serialize(self) -> dict:
        result = super().serialize()
        result["category"] = "database_error"
        return result


class DuplicateError(DatabaseError):
    """Duplicate entry error."""

    def serialize(self) -> dict:
        result = super().serialize()
        result["category"] = "duplicate_error"
        return result


class NotFoundError(DatabaseError):
    """Entity not found error."""

    def serialize(self) -> dict:
        result = super().serialize()
        result["category"] = "not_found_error"
        return result


class ForeignKeyError(DatabaseError):
    """Foreign key constraint error."""

    def serialize(self) -> dict:
        result = super().serialize()
        result["category"] = "foreign_key_error"
        return result
