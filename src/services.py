"""Services layer for database operations."""
from typing import List
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.db import Game, Depot
from src.schemas import GameCreate, DepotCreate
from src.errors import (
    DatabaseError, DuplicateError, NotFoundError, ForeignKeyError, SteamDepoterError
)


class GameService:
    """Service for Game operations."""

    def __init__(self, session: Session):
        self.session = session

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

        try:
            # Check if already exists
            existing = self.session.query(Game).filter(Game.app_id == data.app_id).first()
            if existing:
                raise DuplicateError(f"Game with app_id '{data.app_id}' already exists")

            # Create and save
            game = Game(app_id=data.app_id, name=data.name)
            self.session.add(game)
            self.session.commit()
            return game

        except IntegrityError as e:
            self.session.rollback()
            error_str = str(e)
            if "UNIQUE constraint failed" in error_str:
                raise DuplicateError(f"Game with app_id '{data.app_id}' already exists")
            raise DatabaseError(f"Database integrity error: {error_str}")
        except SQLAlchemyError as e:
            self.session.rollback()
            raise DatabaseError(f"Database error: {str(e)}")

    def get_all_games(self) -> List[Game]:
        """Get all games."""
        try:
            return self.session.query(Game).all()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to fetch games: {str(e)}")

    def delete_game(self, game_id: int) -> None:
        """
        Delete a game and cascade delete its depots.

        Args:
            game_id: Game ID

        Raises:
            NotFoundError: If game not found
            DatabaseError: If deletion fails
        """
        try:
            game = self.session.query(Game).filter(Game.id == game_id).first()
            if not game:
                raise NotFoundError(f"Game with id {game_id} not found")

            self.session.delete(game)
            self.session.commit()

        except SQLAlchemyError as e:
            self.session.rollback()
            raise DatabaseError(f"Failed to delete game: {str(e)}")


class DepotService:
    """Service for Depot operations."""

    def __init__(self, session: Session):
        self.session = session

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

        try:
            # Check if depot already exists
            existing = self.session.query(Depot).filter(Depot.depot_id == data.depot_id).first()
            if existing:
                raise DuplicateError(f"Depot with id '{data.depot_id}' already exists")

            # Check if game exists
            game = self.session.query(Game).filter(Game.app_id == data.app_id).first()
            if not game:
                raise ForeignKeyError(f"Game with app_id '{data.app_id}' not found")

            # Create and save
            depot = Depot(depot_id=data.depot_id, app_id=data.app_id, name=data.name)
            self.session.add(depot)
            self.session.commit()
            return depot

        except IntegrityError as e:
            self.session.rollback()
            error_str = str(e)
            if "UNIQUE constraint failed" in error_str:
                raise DuplicateError(f"Depot with id '{data.depot_id}' already exists")
            if "FOREIGN KEY constraint failed" in error_str:
                raise ForeignKeyError(f"Game with app_id '{data.app_id}' not found")
            raise DatabaseError(f"Database integrity error: {error_str}")
        except SQLAlchemyError as e:
            self.session.rollback()
            raise DatabaseError(f"Database error: {str(e)}")

    def get_all_depots(self) -> List[Depot]:
        """Get all depots."""
        try:
            return self.session.query(Depot).all()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Failed to fetch depots: {str(e)}")

    def delete_depot(self, depot_id: int) -> None:
        """
        Delete a depot.

        Args:
            depot_id: Depot ID

        Raises:
            NotFoundError: If depot not found
            DatabaseError: If deletion fails
        """
        try:
            depot = self.session.query(Depot).filter(Depot.id == depot_id).first()
            if not depot:
                raise NotFoundError(f"Depot with id {depot_id} not found")

            self.session.delete(depot)
            self.session.commit()

        except SQLAlchemyError as e:
            self.session.rollback()
            raise DatabaseError(f"Failed to delete depot: {str(e)}")