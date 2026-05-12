"""Pydantic schemas for validation."""
from pydantic import BaseModel, Field, field_validator


class GameCreate(BaseModel):
    """Schema for creating a game."""
    app_id: str = Field(..., description="Steam app ID (numeric)")
    name: str = Field(..., min_length=1, max_length=255, description="Game name")

    @field_validator("app_id")
    @classmethod
    def validate_app_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("App ID cannot be empty")
        if not v.isdigit():
            raise ValueError("App ID must be numeric")
        if len(v) > 20:
            raise ValueError("App ID cannot exceed 20 characters")
        return v.strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class DepotCreate(BaseModel):
    """Schema for creating a depot."""
    depot_id: str = Field(..., description="Depot ID (numeric)")
    app_id: str = Field(..., description="Associated game app ID")
    name: str = Field(..., min_length=1, max_length=255, description="Depot name")

    @field_validator("depot_id")
    @classmethod
    def validate_depot_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Depot ID cannot be empty")
        if not v.isdigit():
            raise ValueError("Depot ID must be numeric")
        if len(v) > 20:
            raise ValueError("Depot ID cannot exceed 20 characters")
        return v.strip()

    @field_validator("app_id")
    @classmethod
    def validate_app_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("App ID cannot be empty")
        if not v.isdigit():
            raise ValueError("App ID must be numeric")
        return v.strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()