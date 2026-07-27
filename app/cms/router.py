from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.cms.models import ContentItem, ContentStatus, ContentType
from app.core.dependencies import require_roles
from app.core.security import ensure_csrf_token, validate_csrf
from app.database.session import get_db_session


router = APIRouter(prefix="/admin/content", tags=["cms"])


def slugify(value: str) -> str:
    slug = "-".join(value.strip().lower().split())
    return "".join(ch for ch in slug if ch.isalnum() or ch == "-").strip("-") or "untitled"


def list_context(
    request: Request,
    user: User,
    content_type: str,
    items: list[ContentItem],
) -> dict[str, Any]:
    return {
        "current_user": user,
        "csrf_token": ensure_csrf_token(request),
        "content_type": content_type,
        "items": items,
        "title": "Posts" if content_type == ContentType.POST.value else "Pages",
    }


def form_context(
    request: Request,
    user: User,
    content_type: str,
    item: ContentItem | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "current_user": user,
        "csrf_token": ensure_csrf_token(request),
        "content_type": content_type,
        "item": item,
        "error": error,
        "title": "Post" if content_type == ContentType.POST.value else "Page",
    }


def get_content_or_404(session: Session, item_id: int, content_type: str) -> ContentItem:
    item = session.get(ContentItem, item_id)
    if item is None or item.content_type != content_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found.")
    return item


@router.get("/{content_type}")
def list_items(
    content_type: str,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    items = session.scalars(
        select(ContentItem)
        .where(ContentItem.content_type == content_type)
        .order_by(ContentItem.updated_at.desc())
    ).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "cms/list.html",
        list_context(request, user, content_type, items),
    )


@router.get("/{content_type}/new")
def new_item_form(
    content_type: str,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
):
    return request.app.state.templates.TemplateResponse(
        request,
        "cms/form.html",
        form_context(request, user, content_type),
    )


@router.post("/{content_type}")
def create_item(
    content_type: str,
    request: Request,
    title: str = Form(...),
    body: str = Form(""),
    status_value: str = Form(ContentStatus.DRAFT.value),
    csrf_token: str = Form(...),
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    title = title.strip()
    if not title:
        return request.app.state.templates.TemplateResponse(
            request,
            "cms/form.html",
            form_context(request, user, content_type, error="Title is required."),
            status_code=400,
        )

    base_slug = slugify(title)
    slug = base_slug
    counter = 2
    while session.scalar(select(ContentItem).where(ContentItem.slug == slug)) is not None:
        slug = f"{base_slug}-{counter}"
        counter += 1

    item = ContentItem(
        title=title,
        slug=slug,
        body=body.strip(),
        content_type=content_type,
        status=status_value if status_value in {ContentStatus.DRAFT.value, ContentStatus.PUBLISHED.value} else ContentStatus.DRAFT.value,
    )
    session.add(item)
    session.commit()

    return RedirectResponse(url=f"/admin/content/{content_type}", status_code=303)


@router.get("/{content_type}/{item_id}/edit")
def edit_item_form(
    content_type: str,
    item_id: int,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    item = get_content_or_404(session, item_id, content_type)
    return request.app.state.templates.TemplateResponse(
        request,
        "cms/form.html",
        form_context(request, user, content_type, item=item),
    )


@router.post("/{content_type}/{item_id}")
def update_item(
    content_type: str,
    item_id: int,
    request: Request,
    title: str = Form(...),
    body: str = Form(""),
    status_value: str = Form(ContentStatus.DRAFT.value),
    csrf_token: str = Form(...),
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    item = get_content_or_404(session, item_id, content_type)
    item.title = title.strip()
    item.body = body.strip()
    item.status = status_value if status_value in {ContentStatus.DRAFT.value, ContentStatus.PUBLISHED.value} else ContentStatus.DRAFT.value
    session.commit()
    return RedirectResponse(url=f"/admin/content/{content_type}", status_code=303)
