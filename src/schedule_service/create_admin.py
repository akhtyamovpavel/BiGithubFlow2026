"""Create the initial administrator from an interactive terminal."""

import asyncio
import getpass

from sqlalchemy import select

from schedule_service.core.auth import hash_password
from schedule_service.core.database import async_engine, async_session_factory
from schedule_service.models.user import User, UserRole


async def create_admin(username: str, password: str) -> None:
    async with async_session_factory.begin() as session:
        existing = await session.scalar(select(User.id).limit(1))
        if existing is not None:
            raise ValueError("Initial administrator can only be created when no users exist")
        session.add(
            User(
                username=username,
                password_hash=hash_password(password),
                role=UserRole.ADMIN.value,
                is_active=True,
            )
        )
    await async_engine.dispose()


def main() -> None:
    username = input("Username: ")
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if not username or len(username) > 100 or any(char.isspace() for char in username):
        raise ValueError("Username must contain 1 to 100 non-whitespace characters")
    if len(password) < 8 or len(password) > 128 or password != confirmation:
        raise ValueError("Passwords must match and contain 8 to 128 characters")
    asyncio.run(create_admin(username, password))
    print("Administrator created")


if __name__ == "__main__":
    main()
