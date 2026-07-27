from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.models import User, UserRole
from app.cms.models import ContentItem, ContentType
from app.cms.router import unique_slug
from app.cms.visibility import normalize_status_and_publish_at, publicly_visible_clause
from app.core.dependencies import get_current_user, require_roles
from app.database.session import get_db_session
from app.plugins.hooks import HookRegistry


router = APIRouter(prefix="/api/v1", tags=["api"])

STAFF_ROLES = {UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value}


class ContentOut(BaseModel):
    id: int
    title: str
    slug: str
    body: str
    excerpt: str | None
    meta_title: str | None
    meta_description: str | None
    content_type: str
    status: str
    publish_at: datetime | None
    author_id: int | None
    created_at: datetime
    updated_at: datetime
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ContentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = ""
    excerpt: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    status: Literal["draft", "published", "scheduled"] = "draft"
    publish_at: datetime | None = None


class ContentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = None
    excerpt: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    status: Literal["draft", "published", "scheduled"] | None = None
    publish_at: datetime | None = None


def serialize_item(item: ContentItem) -> ContentOut:
    return ContentOut(
        id=item.id,
        title=item.title,
        slug=item.slug,
        body=item.body,
        excerpt=item.excerpt,
        meta_title=item.meta_title,
        meta_description=item.meta_description,
        content_type=item.content_type,
        status=item.status,
        publish_at=item.publish_at,
        author_id=item.author_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        categories=[c.name for c in item.categories],
        tags=[t.name for t in item.tags],
    )


def get_optional_user(request: Request, session: Session) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return session.get(User, user_id)


def get_item(session: Session, content_type: str, item_id: int) -> ContentItem:
    item = session.scalar(
        select(ContentItem)
        .where(ContentItem.id == item_id, ContentItem.content_type == content_type)
        .options(
            selectinload(ContentItem.categories),
            selectinload(ContentItem.tags),
            selectinload(ContentItem.author),
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found.")
    return item


def list_items(
    request: Request,
    session: Session,
    content_type: str,
    status_filter: str | None,
) -> list[ContentOut]:
    query = (
        select(ContentItem)
        .where(ContentItem.content_type == content_type)
        .options(
            selectinload(ContentItem.categories),
            selectinload(ContentItem.tags),
            selectinload(ContentItem.author),
        )
        .order_by(ContentItem.updated_at.desc())
    )
    user = get_optional_user(request, session)
    is_staff = user is not None and user.role in STAFF_ROLES
    if is_staff and status_filter:
        query = query.where(ContentItem.status == status_filter)
    elif not is_staff:
        query = query.where(publicly_visible_clause())

    return [serialize_item(item) for item in session.scalars(query).all()]


def get_by_slug(session: Session, content_type: str, slug: str) -> ContentOut:
    item = session.scalar(
        select(ContentItem)
        .where(
            ContentItem.slug == slug,
            ContentItem.content_type == content_type,
            publicly_visible_clause(),
        )
        .options(
            selectinload(ContentItem.categories),
            selectinload(ContentItem.tags),
            selectinload(ContentItem.author),
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found.")
    return serialize_item(item)


def create_item(
    request: Request,
    session: Session,
    user: User,
    content_type: str,
    payload: ContentCreate,
) -> ContentOut:
    status_value, publish_at = normalize_status_and_publish_at(payload.status, payload.publish_at)
    hooks: HookRegistry = request.app.state.hooks
    item = ContentItem(
        title=payload.title.strip(),
        slug=unique_slug(session, payload.title.strip()),
        body=payload.body or "",
        excerpt=(payload.excerpt or "").strip() or None,
        meta_title=(payload.meta_title or "").strip() or None,
        meta_description=(payload.meta_description or "").strip() or None,
        content_type=content_type,
        status=status_value,
        publish_at=publish_at,
        author_id=user.id,
    )
    hooks.do_action("content.before_save", item, user, is_new=True)
    session.add(item)
    session.commit()
    session.refresh(item)
    item = get_item(session, content_type, item.id)
    hooks.do_action("content.after_save", item, user, is_new=True)
    return serialize_item(item)


def update_item(
    request: Request,
    session: Session,
    user: User,
    content_type: str,
    item_id: int,
    payload: ContentUpdate,
) -> ContentOut:
    item = get_item(session, content_type, item_id)
    hooks: HookRegistry = request.app.state.hooks
    if payload.title is not None:
        item.title = payload.title.strip()
    if payload.body is not None:
        item.body = payload.body
    if payload.excerpt is not None:
        item.excerpt = payload.excerpt.strip() or None
    if payload.meta_title is not None:
        item.meta_title = payload.meta_title.strip() or None
    if payload.meta_description is not None:
        item.meta_description = payload.meta_description.strip() or None
    status_value = payload.status if payload.status is not None else item.status
    publish_at = payload.publish_at if payload.publish_at is not None else item.publish_at
    if payload.status is not None or payload.publish_at is not None:
        item.status, item.publish_at = normalize_status_and_publish_at(status_value, publish_at)
    hooks.do_action("content.before_save", item, user, is_new=False)
    session.commit()
    item = get_item(session, content_type, item.id)
    hooks.do_action("content.after_save", item, user, is_new=False)
    return serialize_item(item)


@router.get("/me")
def api_me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"id": user.id, "email": user.email, "role": user.role}


@router.get("/posts", response_model=list[ContentOut])
def list_posts(
    request: Request,
    session: Session = Depends(get_db_session),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[ContentOut]:
    return list_items(request, session, ContentType.POST.value, status_filter)


@router.get("/pages", response_model=list[ContentOut])
def list_pages(
    request: Request,
    session: Session = Depends(get_db_session),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[ContentOut]:
    return list_items(request, session, ContentType.PAGE.value, status_filter)


@router.get("/posts/{slug}", response_model=ContentOut)
def get_post(slug: str, session: Session = Depends(get_db_session)) -> ContentOut:
    return get_by_slug(session, ContentType.POST.value, slug)


@router.get("/pages/{slug}", response_model=ContentOut)
def get_page(slug: str, session: Session = Depends(get_db_session)) -> ContentOut:
    return get_by_slug(session, ContentType.PAGE.value, slug)


@router.post("/posts", response_model=ContentOut, status_code=status.HTTP_201_CREATED)
def create_post(
    payload: ContentCreate,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
) -> ContentOut:
    return create_item(request, session, user, ContentType.POST.value, payload)


@router.post("/pages", response_model=ContentOut, status_code=status.HTTP_201_CREATED)
def create_page(
    payload: ContentCreate,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
) -> ContentOut:
    return create_item(request, session, user, ContentType.PAGE.value, payload)


@router.patch("/posts/{item_id}", response_model=ContentOut)
def update_post(
    item_id: int,
    payload: ContentUpdate,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
) -> ContentOut:
    return update_item(request, session, user, ContentType.POST.value, item_id, payload)


@router.patch("/pages/{item_id}", response_model=ContentOut)
def update_page(
    item_id: int,
    payload: ContentUpdate,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
) -> ContentOut:
    return update_item(request, session, user, ContentType.PAGE.value, item_id, payload)


@router.delete("/posts/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    item_id: int,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
) -> None:
    item = get_item(session, ContentType.POST.value, item_id)
    session.delete(item)
    session.commit()


@router.delete("/pages/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_page(
    item_id: int,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
) -> None:
    item = get_item(session, ContentType.PAGE.value, item_id)
    session.delete(item)
    session.commit()
