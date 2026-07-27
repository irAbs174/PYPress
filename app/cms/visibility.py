from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_
from sqlalchemy.sql import ColumnElement

from app.cms.models import ContentItem, ContentStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def publicly_visible_clause(now: datetime | None = None) -> ColumnElement[bool]:
    """Published now, or scheduled with publish_at in the past."""
    moment = now or utcnow()
    return or_(
        ContentItem.status == ContentStatus.PUBLISHED.value,
        and_(
            ContentItem.status == ContentStatus.SCHEDULED.value,
            ContentItem.publish_at.is_not(None),
            ContentItem.publish_at <= moment,
        ),
    )


def parse_publish_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_status_and_publish_at(
    status_value: str,
    publish_at: datetime | None,
) -> tuple[str, datetime | None]:
    allowed = {
        ContentStatus.DRAFT.value,
        ContentStatus.PUBLISHED.value,
        ContentStatus.SCHEDULED.value,
    }
    status = status_value if status_value in allowed else ContentStatus.DRAFT.value
    if status == ContentStatus.SCHEDULED.value:
        if publish_at is None:
            return ContentStatus.DRAFT.value, None
        if publish_at <= utcnow():
            return ContentStatus.PUBLISHED.value, publish_at
        return status, publish_at
    if status == ContentStatus.DRAFT.value:
        return status, publish_at
    return status, publish_at
