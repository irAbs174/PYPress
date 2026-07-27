from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.cms.models import Category, ContentItem, ContentStatus, ContentType, Tag
from app.cms.router import unique_slug
from app.core.dependencies import get_current_user, require_roles
from app.core.security import ensure_csrf_token, validate_csrf
from app.database.session import get_db_session
from app.plugins.hooks import HookRegistry


router = APIRouter(prefix="/admin", tags=["admin"])


def dashboard_context(
    request: Request,
    user: User,
    session: Session,
    *,
    draft_error: str | None = None,
    draft_saved: bool = False,
) -> dict:
    total_posts = session.scalar(
        select(func.count()).select_from(ContentItem).where(ContentItem.content_type == ContentType.POST.value)
    ) or 0
    total_pages = session.scalar(
        select(func.count()).select_from(ContentItem).where(ContentItem.content_type == ContentType.PAGE.value)
    ) or 0
    total_categories = session.scalar(select(func.count()).select_from(Category)) or 0
    total_tags = session.scalar(select(func.count()).select_from(Tag)) or 0
    recent_posts = session.scalars(
        select(ContentItem)
        .where(ContentItem.content_type == ContentType.POST.value)
        .order_by(ContentItem.updated_at.desc())
        .limit(5)
    ).all()

    return {
        "current_user": user,
        "csrf_token": ensure_csrf_token(request),
        "total_posts": total_posts,
        "total_pages": total_pages,
        "total_categories": total_categories,
        "total_tags": total_tags,
        "recent_posts": recent_posts,
        "draft_error": draft_error,
        "draft_saved": draft_saved,
    }


@router.get("")
def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    return request.app.state.templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        dashboard_context(request, user, session, draft_saved=request.query_params.get("draft") == "1"),
    )


@router.post("/quick-draft")
def quick_draft(
    request: Request,
    title: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    body: Annotated[str, Form()] = "",
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    title = title.strip()
    if not title:
        return request.app.state.templates.TemplateResponse(
            request,
            "admin/dashboard.html",
            dashboard_context(request, user, session, draft_error="Title is required."),
            status_code=400,
        )

    hooks: HookRegistry = request.app.state.hooks
    item = ContentItem(
        title=title,
        slug=unique_slug(session, title),
        body=body.strip(),
        content_type=ContentType.POST.value,
        status=ContentStatus.DRAFT.value,
        author_id=user.id,
    )
    hooks.do_action("content.before_save", item, user, is_new=True)
    session.add(item)
    session.commit()
    session.refresh(item)
    hooks.do_action("content.after_save", item, user, is_new=True)
    return RedirectResponse(url="/admin?draft=1", status_code=303)
