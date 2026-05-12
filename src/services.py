"""Services layer for database operations."""
from typing import List, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.db import Game, Depot, Manifest, ManifestFile
from src.db.validation import GameCreate, DepotCreate
from src.errors.errors import (
    DatabaseError, DuplicateError, NotFoundError, ForeignKeyError
)


class BaseService:
    """Base service with common database operations."""

    def __init__(self, session: Session):
        self.session = session

    def _handle_db_error(self, error: Exception) -> None:
        error_str = str(error)

        if isinstance(error, IntegrityError):
            if "UNIQUE constraint failed" in error_str:
                raise DuplicateError("Duplicate entry")
            if "FOREIGN KEY constraint failed" in error_str:
                raise ForeignKeyError("Referenced record not found")
            raise DatabaseError(f"Database integrity error: {error_str}")

        if isinstance(error, SQLAlchemyError):
            self.session.rollback()
            raise DatabaseError(f"Database error: {error_str}")

        raise error

    def _create(self, model: type, **kwargs):
        try:
            obj = model(**kwargs)
            self.session.add(obj)
            self.session.commit()
            return obj
        except (IntegrityError, SQLAlchemyError) as e:
            self.session.rollback()
            self._handle_db_error(e)

    def _get_all(self, model: type) -> List:
        try:
            return self.session.query(model).all()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to fetch {model.__name__}: {str(e)}")

    def _delete(self, model: type, id_value: int) -> None:
        try:
            obj = self.session.query(model).filter(model.id == id_value).first()
            if not obj:
                raise NotFoundError(f"{model.__name__} not found")

            self.session.delete(obj)
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            raise DatabaseError(f"Failed to delete {model.__name__}: {str(e)}")


class GameService(BaseService):

    def create_game(self, props: dict) -> Any | None:
        data = GameCreate(**props)
        return self._create(Game, app_id=data.app_id, name=data.name)

    def get_all_games(self) -> List[Game]:
        """Get all games."""
        return self._get_all(Game)

    def delete_game(self, game_id: int) -> None:
        self._delete(Game, game_id)


class DepotService(BaseService):

    def create_depot(self, props: dict) -> Any | None:
        data = DepotCreate(**props)

        game = self.session.query(Game).filter(Game.app_id == data.app_id).first()
        if not game:
            raise ForeignKeyError(f"Game with app_id '{data.app_id}' not found")

        return self._create(Depot, depot_id=data.depot_id, app_id=data.app_id, name=data.name)

    def get_all_depots(self) -> List[Depot]:
        return self._get_all(Depot)

    def delete_depot(self, depot_id: int) -> None:
        self._delete(Depot, depot_id)


class ManifestService(BaseService):
    """Service for handling Steam Manifests."""

    def save_manifests(self, app_id: str, manifests: dict) -> None:
        """
        Saves or updates manifests and their files for a given app.
        manifests is a dict of {depot_id: ManifestDataClass}
        """
        try:
            for depot_id_int, m_data in manifests.items():
                depot_id = str(depot_id_int)
                # Ensure depot exists
                depot = self.session.query(Depot).filter(Depot.depot_id == depot_id).first()
                if not depot:
                    # Create a default depot if it doesn't exist? 
                    # For now, let's assume it should exist or we create it with app_id
                    depot = Depot(depot_id=depot_id, app_id=app_id, name=f"Depot {depot_id}")
                    self.session.add(depot)
                    self.session.flush()

                # Check if manifest exists
                manifest_id = str(m_data.manifest_id)
                manifest = self.session.query(Manifest).filter(Manifest.manifest_id == manifest_id).first()
                
                if manifest:
                    # Clear existing files for this manifest to update them
                    self.session.query(ManifestFile).filter(ManifestFile.manifest_id == manifest_id).delete()
                else:
                    manifest = Manifest(manifest_id=manifest_id, depot_id=depot_id)
                    self.session.add(manifest)

                # Update manifest info
                manifest.date_str = m_data.date
                manifest.total_files = m_data.total_files
                manifest.total_chunks = m_data.total_chunks
                manifest.total_bytes_on_disk = m_data.total_bytes_on_disk
                manifest.total_bytes_compressed = m_data.total_bytes_compressed

                # Add files
                for f_data in m_data.files:
                    m_file = ManifestFile(
                        manifest_id=manifest_id,
                        name=f_data.name,
                        size=f_data.size,
                        chunks=f_data.chunks,
                        sha=f_data.sha,
                        flags=f_data.flags
                    )
                    self.session.add(m_file)

            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise DatabaseError(f"Failed to save manifests: {str(e)}")
