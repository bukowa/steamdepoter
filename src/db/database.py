"""Core database module."""
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session

from .schema import Base


class Database:
    """Database connection and session management."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database.

        Args:
            db_path: Path to SQLite database file. Defaults to data/steamdepoter.db
        """
        if db_path is None:
            db_path = "data/steamdepoter.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # SQLAlchemy engine
        self.engine: Engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        # Session factory
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    def create_tables(self) -> None:
        """Create all tables from schema."""
        Base.metadata.create_all(self.engine)

    def drop_tables(self) -> None:
        """Drop all tables. WARNING: Destructive operation."""
        Base.metadata.drop_all(self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def close(self) -> None:
        """Close database connection."""
        self.engine.dispose()

