from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cms.models import SiteSetting


def get_setting(session: Session, key: str, default: str = "") -> str:
    setting = session.scalar(select(SiteSetting).where(SiteSetting.key == key))
    if setting is None:
        return default
    return setting.value


def setting_exists(session: Session, key: str) -> bool:
    return session.scalar(select(SiteSetting).where(SiteSetting.key == key)) is not None


def set_setting(session: Session, key: str, value: str) -> SiteSetting:
    setting = session.scalar(select(SiteSetting).where(SiteSetting.key == key))
    if setting is None:
        setting = SiteSetting(key=key, value=value)
        session.add(setting)
    else:
        setting.value = value
    session.commit()
    session.refresh(setting)
    return setting


def get_enabled_plugins(session: Session, defaults: set[str] | None = None) -> set[str]:
    if not setting_exists(session, "enabled_plugins"):
        return set(defaults or set())
    raw = get_setting(session, "enabled_plugins", "")
    if not raw.strip():
        return set()
    return {name.strip() for name in raw.split(",") if name.strip()}


def set_enabled_plugins(session: Session, plugin_names: list[str]) -> None:
    set_setting(session, "enabled_plugins", ",".join(sorted(plugin_names)))
