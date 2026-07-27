from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.cms.settings import get_setting, set_setting
from app.core.config import get_settings
from app.core.dependencies import require_roles
from app.core.security import ensure_csrf_token, validate_csrf
from app.database.session import get_db_session
from app.themes import build_templates, discover_themes, get_theme_path


router = APIRouter(prefix="/admin/themes", tags=["themes"])


@router.get("")
def list_themes(
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    settings = get_settings()
    active = get_setting(session, "active_theme", settings.default_theme)
    return request.app.state.templates.TemplateResponse(
        request,
        "themes/list.html",
        {
            "current_user": user,
            "csrf_token": ensure_csrf_token(request),
            "themes": discover_themes(),
            "active_theme": active,
        },
    )


@router.post("/activate")
def activate_theme(
    request: Request,
    theme_name: str = Form(...),
    csrf_token: str = Form(...),
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    if get_theme_path(theme_name) is None:
        raise HTTPException(status_code=400, detail="Theme not found.")
    set_setting(session, "active_theme", theme_name)
    request.app.state.templates = build_templates(theme_name)
    request.app.state.active_theme = theme_name
    return RedirectResponse(url="/admin/themes", status_code=303)
