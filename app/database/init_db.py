from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.cms.models import SiteSetting
from app.core.config import get_settings
from app.core.security import hash_password
from app.database.base import Base
from app.database.session import engine

# Ensure all models are registered on Base.metadata
from app.cms import models as _cms_models  # noqa: F401
from app.auth import models as _auth_models  # noqa: F401


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


def seed_defaults(session: Session) -> None:
    settings = get_settings()
    defaults = {
        "site_title": settings.app_name,
        "site_tagline": "A Python CMS",
        "active_theme": settings.default_theme,
    }
    for key, value in defaults.items():
        existing = session.scalar(select(SiteSetting).where(SiteSetting.key == key))
        if existing is None:
            session.add(SiteSetting(key=key, value=value))
    session.commit()
