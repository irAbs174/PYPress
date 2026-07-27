from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.cms.models import ContentItem, ContentStatus, ContentType
from app.core.dependencies import get_current_user
from app.core.security import ensure_csrf_token
from app.database.session import get_db_session


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("")
def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    total_posts = session.scalar(
        select(func.count()).select_from(ContentItem).where(ContentItem.content_type == ContentType.POST.value)
    ) or 0
    total_pages = session.scalar(
        select(func.count()).select_from(ContentItem).where(ContentItem.content_type == ContentType.PAGE.value)
    ) or 0
    published_count = session.scalar(
        select(func.count()).select_from(ContentItem).where(ContentItem.status == ContentStatus.PUBLISHED.value)
    ) or 0
    recent_items = session.scalars(
        select(ContentItem).order_by(ContentItem.updated_at.desc()).limit(5)
    ).all()

    return request.app.state.templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "current_user": user,
            "csrf_token": ensure_csrf_token(request),
            "total_posts": total_posts,
            "total_pages": total_pages,
            "published_count": published_count,
            "recent_items": recent_items,
        },
    )
