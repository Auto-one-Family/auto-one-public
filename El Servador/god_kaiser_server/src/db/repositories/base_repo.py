"""
Base Repository with Generic CRUD Operations
"""

import uuid
from typing import Any, Generic, Optional, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..base import Base

# Generic type for model classes
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Base Repository with generic CRUD operations.

    Provides standard database operations for any SQLAlchemy model.
    Should be extended by specific repositories for custom queries.

    Type Parameters:
        ModelType: The SQLAlchemy model class this repository manages
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository.

        Args:
            model: The SQLAlchemy model class
            session: Async database session
        """
        self.model = model
        self.session = session

    async def create(self, **data: Any) -> ModelType:
        """
        Create a new record.

        Args:
            **data: Model field values

        Returns:
            Created model instance

        Raises:
            DatabaseException: If creation fails
        """
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def get_by_id(self, id: uuid.UUID) -> Optional[ModelType]:
        """
        Get record by ID.

        Args:
            id: Record UUID

        Returns:
            Model instance or None if not found
        """
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """
        Get all records with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of model instances
        """
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, id: uuid.UUID, **data: Any) -> Optional[ModelType]:
        """
        Update a record by ID.

        Args:
            id: Record UUID
            **data: Fields to update

        Returns:
            Updated model instance or None if not found
        """
        instance = await self.get_by_id(id)
        if instance is None:
            return None

        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, id: uuid.UUID) -> bool:
        """
        Delete a record by ID.

        Args:
            id: Record UUID

        Returns:
            True if deleted, False if not found
        """
        instance = await self.get_by_id(id)
        if instance is None:
            return False

        await self.session.delete(instance)
        await self.session.flush()
        return True

    async def count(self) -> int:
        """
        Count total records.

        Returns:
            Total number of records
        """
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, id: uuid.UUID) -> bool:
        """
        Check if record exists.

        Args:
            id: Record UUID

        Returns:
            True if exists, False otherwise
        """
        stmt = select(func.count()).select_from(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0
