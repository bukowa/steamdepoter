"""Database schema definitions."""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, BigInteger
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
    manifests = relationship("Manifest", back_populates="depot", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Depot(depot_id={self.depot_id}, name={self.name})>"


class Manifest(Base):
    """Steam Manifest model."""

    __tablename__ = "manifests"

    id = Column(Integer, primary_key=True)
    manifest_id = Column(String, unique=True, nullable=False, index=True)
    depot_id = Column(String, ForeignKey("depots.depot_id"), nullable=False)
    date_str = Column(String)
    total_files = Column(Integer)
    total_chunks = Column(Integer)
    total_bytes_on_disk = Column(BigInteger)
    total_bytes_compressed = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    depot = relationship("Depot", back_populates="manifests")
    files = relationship("ManifestFile", back_populates="manifest", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Manifest(manifest_id={self.manifest_id}, depot_id={self.depot_id})>"


class ManifestFile(Base):
    """File within a Steam Manifest."""

    __tablename__ = "manifest_files"

    id = Column(Integer, primary_key=True)
    manifest_id = Column(String, ForeignKey("manifests.manifest_id"), nullable=False)
    name = Column(String, nullable=False, index=True)
    size = Column(BigInteger, nullable=False)
    chunks = Column(Integer)
    sha = Column(String(40))
    flags = Column(Integer)

    manifest = relationship("Manifest", back_populates="files")

    def __repr__(self):
        return f"<ManifestFile(name={self.name}, size={self.size})>"

