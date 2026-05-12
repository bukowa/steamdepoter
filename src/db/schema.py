"""Database schema definitions."""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Game(Base):
    """Steam Game model."""

    __tablename__ = "games"

    id = Column(Integer, primary_key=True)
    app_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    depots = relationship("Depot", back_populates="game", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Game(app_id={self.app_id}, name={self.name})>"


class Depot(Base):
    """Steam Depot model."""

    __tablename__ = "depots"

    id = Column(Integer, primary_key=True)
    depot_id = Column(String, unique=True, nullable=False, index=True)
    app_id = Column(String, ForeignKey("games.app_id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    game = relationship("Game", back_populates="depots")

    def __repr__(self):
        return f"<Depot(depot_id={self.depot_id}, name={self.name})>"

