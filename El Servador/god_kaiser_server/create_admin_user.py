#!/usr/bin/env python3
"""
Create admin user for testing
"""
import os
import asyncio
from src.db.session import get_session
from src.db.models.user import User
from src.core.security import get_password_hash

async def create_admin():
    async for session in get_session():
        # Check if user exists
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.username == "testadmin"))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print("User 'testadmin' already exists")
            return

        # Create new admin user
        user = User(
            username="testadmin",
            email="testadmin@test.local",
            hashed_password=get_password_hash(os.environ.get("E2E_TEST_PASSWORD", "")),
            full_name="Test Admin",
            is_active=True
        )
        session.add(user)
        await session.commit()
        print("Admin user 'testadmin' created successfully")
        break

if __name__ == "__main__":
    asyncio.run(create_admin())
