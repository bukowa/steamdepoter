"""Services layer for database operations."""
from typing import List, TypeVar
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.db import Game, Depot
from src.schemas import GameCreate, DepotCreate
from src.errors import (
    DatabaseError, DuplicateError, NotFoundError, ForeignKeyError, SteamDepoterError
)

T = TypeVar("T")


class BaseService:
    """Base service with common database operations."""

    def __init__(self, session: Session):
        self.session = session

    def _handle_db_error(self, error: Exception, context: str = "") -> None:
        """Convert database errors to domain errors."""
        error_str = str(error)

        if isinstance(error, IntegrityError):
            if "UNIQUE constraint failed" in error_str:
                raise DuplicateError(f"{context} already exists")
            if "FOREIGN KEY constraint failed" in error_str:
                raise ForeignKeyError(f"Referenced record not found: {context}")
            raise DatabaseError(f"Database integrity error: {error_str}")

        if isinstance(error, SQLAlchemyError):
            self.session.rollback()
            raise DatabaseError(f"Database error: {error_str}")

        raise error

    def _create(self, model: type, **kwargs):
        """Generic create operation with error handling."""
        try:
            obj = model(**kwargs)
            self.session.add(obj)
            self.session.commit()
            return obj
        except (IntegrityError, SQLAlchemyError) as e:
            self.session.rollback()
            self._handle_db_error(e)

    def _get_all(self, model: type) -> List:
        """Generic get all operation."""
        try:
            return self.session.query(model).all()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to fetch {model.__name__}: {str(e)}")

    def _delete(self, model: type, id_value: int, id_field=None) -> None:
        """Generic delete operation."""
        if id_field is None:
            id_field = model.id

        try:
            obj = self.session.query(model).filter(id_field == id_value).first()
            if not obj:
                raise NotFoundError(f"{model.__name__} not found")

            self.session.delete(obj)
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            raise DatabaseError(f"Failed to delete {model.__name__}: {str(e)}")


class GameService(BaseService):
    """Service for Game operations."""

    def create_game(self, app_id: str, name: str) -> Game:
        """
        Create a new game.

        Args:
            app_id: Steam app ID
            name: Game name

        Returns:
            Created Game object

        Raises:
            ValueError: If validation fails
            DuplicateError: If app_id already exists
            DatabaseError: If database operation fails
        """
        # Validate using Pydantic
        try:
            data = GameCreate(app_id=app_id, name=name)
        except PydanticValidationError as e:
            raise ValueError(str(e))

        # Check if already exists
        existing = self.session.query(Game).filter(Game.app_id == data.app_id).first()
        if existing:
            raise DuplicateError(f"Game with app_id '{data.app_id}' already exists")

        return self._create(Game, app_id=data.app_id, name=data.name)

    def get_all_games(self) -> List[Game]:
        """Get all games."""
        return self._get_all(Game)

    def delete_game(self, game_id: int) -> None:
        """
        Delete a game and cascade delete its depots.

        Args:
            game_id: Game ID

        Raises:
            NotFoundError: If game not found
            DatabaseError: If deletion fails
        """
        self._delete(Game, game_id)


class DepotService(BaseService):
    """Service for Depot operations."""

    def create_depot(self, depot_id: str, app_id: str, name: str) -> Depot:
        """
        Create a new depot.

        Args:
            depot_id: Depot ID
            app_id: Associated game app_id (must exist)
            name: Depot name

        Returns:
            Created Depot object

        Raises:
            ValueError: If validation fails
            DuplicateError: If depot_id already exists
            ForeignKeyError: If app_id doesn't exist
            DatabaseError: If database operation fails
        """
        # Validate using Pydantic
        try:
            data = DepotCreate(depot_id=depot_id, app_id=app_id, name=name)
        except PydanticValidationError as e:
            raise ValueError(str(e))

        # Check if depot already exists
        existing = self.session.query(Depot).filter(Depot.depot_id == data.depot_id).first()
        if existing:
            raise DuplicateError(f"Depot with id '{data.depot_id}' already exists")

        # Check if game exists
        game = self.session.query(Game).filter(Game.app_id == data.app_id).first()
        if not game:
            raise ForeignKeyError(f"Game with app_id '{data.app_id}' not found")

        return self._create(Depot, depot_id=data.depot_id, app_id=data.app_id, name=data.name)

    def get_all_depots(self) -> List[Depot]:
        """Get all depots."""
        return self._get_all(Depot)

    def delete_depot(self, depot_id: int) -> None:
        """
        Delete a depot.

        Args:
            depot_id: Depot ID

        Raises:
            NotFoundError: If depot not found
            DatabaseError: If deletion fails
        """
        self._delete(Depot, depot_id)
