#!/usr/bin/env python3
"""
Create fresh database with all tables
"""
import asyncio
from src.db.base import Base
from src.db.session import get_engine

# Import all models to register them with Base.metadata
from src.db import models  # noqa: F401

async def create_tables():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_tables())
