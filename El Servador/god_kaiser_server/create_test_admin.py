"""
Create test admin user for testing
"""
import os
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.db.session import get_session
from src.db.repositories.user_repo import UserRepository
from src.core.security import get_password_hash


async def create_test_admin():
    """Create test_admin user"""
    async for session in get_session():
        user_repo = UserRepository(session)
        
        # Delete old test_admin if exists (to recreate with valid email)
        existing = await user_repo.get_by_username('test_admin')
        if existing:
            print(f'[INFO] Deleting old test_admin (ID: {existing.id})')
            await user_repo.delete(existing.id)
            await session.commit()
        
        # Create new admin with VALID email
        user = await user_repo.create(
            email='test_admin@example.com',  # Valid TLD!
            username='test_admin',
            password_hash=get_password_hash(os.environ.get("E2E_TEST_PASSWORD", "")),
            role='admin',
            is_active=True
        )
        await session.commit()
        print(f'[OK] New admin created: {user.username} (ID: {user.id})')
        print(f'   Email: {user.email}')
        print(f'   Password: [set E2E_TEST_PASSWORD env var]')
        return user.id


if __name__ == '__main__':
    user_id = asyncio.run(create_test_admin())
    print(f'\nUser ID: {user_id}')

