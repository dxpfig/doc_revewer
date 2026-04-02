from db.session import async_session_maker
from models.database import User
from sqlalchemy import select
import hashlib


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


async def seed_default_users():
    """Create default admin and user accounts for development."""
    async with async_session_maker() as db:
        result = await db.execute(select(User))
        if result.scalars().first() is not None:
            return

        # 密码与用户名相同
        default_users = [
            {"username": "admin", "role": "admin"},
            {"username": "user1", "role": "user"},
        ]

        for u in default_users:
            user = User(
                username=u["username"],
                hashed_password=hash_password(u["username"]),
                role=u["role"],
            )
            db.add(user)

        await db.commit()