from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.core.config import get_settings
from app.core.security import hash_password
from app.database.base import Base
from app.database.session import engine


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def seed_admin(session: Session) -> None:
    settings = get_settings()
    existing_user = session.scalar(select(User).where(User.email == settings.admin_email))
    if existing_user:
        return

    session.add(
        User(
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            role=UserRole.ADMIN.value,
        )
    )
    session.commit()
