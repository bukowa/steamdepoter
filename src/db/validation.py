"""Pydantic schemas for validation."""
from pydantic import BaseModel, Field, field_validator


def validate_numeric_id(v: str, max_len: int = 20) -> str:
    """Validate numeric ID fields."""
    if not v or not v.strip():
        raise ValueError("ID cannot be empty")
    if not v.isdigit():
        raise ValueError("ID must be numeric")
    if len(v) > max_len:
        raise ValueError(f"ID cannot exceed {max_len} characters")
    return v.strip()


def validate_name(v: str) -> str:
    """Validate name fields."""
    if not v or not v.strip():
        raise ValueError("Name cannot be empty")
    return v.strip()


class GameCreate(BaseModel):
    """Schema for creating a game."""
    app_id: str = Field(..., description="Steam app ID (numeric)")
    name: str = Field(..., min_length=1, max_length=255, description="Game name")

    @field_validator("app_id")
    @classmethod
    def val_app_id(cls, v: str) -> str:
        return validate_numeric_id(v)

    @field_validator("name")
    @classmethod
    def val_name(cls, v: str) -> str:
        return validate_name(v)


class DepotCreate(BaseModel):
    """Schema for creating a depot."""
    depot_id: str = Field(..., description="Depot ID (numeric)")
    app_id: str = Field(..., description="Associated game app ID")
    name: str = Field(..., min_length=1, max_length=255, description="Depot name")
    os: str | None = Field(None, description="Operating system (optional)")
    language: str | None = Field(None, description="Language (optional)")

    @field_validator("depot_id", "app_id")
    @classmethod
    def val_numeric_ids(cls, v: str) -> str:
        return validate_numeric_id(v)

    @field_validator("name")
    @classmethod
    def val_name(cls, v: str) -> str:
        return validate_name(v)
