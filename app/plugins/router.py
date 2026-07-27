from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.cms.settings import get_enabled_plugins, set_enabled_plugins
from app.core.dependencies import require_roles
from app.core.security import ensure_csrf_token, validate_csrf
from app.database.session import get_db_session
from app.plugins import default_enabled_plugins, discover_plugins, load_plugins
from app.plugins.hooks import HookRegistry


router = APIRouter(prefix="/admin/plugins", tags=["plugins"])


@router.get("")
def list_plugins(
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    enabled = get_enabled_plugins(session, defaults=default_enabled_plugins())
    return request.app.state.templates.TemplateResponse(
        request,
        "plugins/list.html",
        {
            "current_user": user,
            "csrf_token": ensure_csrf_token(request),
            "plugins": discover_plugins(),
            "enabled_plugins": enabled,
        },
    )


@router.post("/toggle")
def toggle_plugin(
    request: Request,
    plugin_name: str = Form(...),
    csrf_token: str = Form(...),
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    enabled = get_enabled_plugins(session, defaults=default_enabled_plugins())
    if plugin_name in enabled:
        enabled.discard(plugin_name)
    else:
        enabled.add(plugin_name)

    set_enabled_plugins(session, sorted(enabled))

    hooks: HookRegistry = request.app.state.hooks
    hooks.clear()
    loaded = load_plugins(request.app, hooks, enabled)
    request.app.state.loaded_plugins = loaded
    hooks.do_action("app.startup", request.app)

    return RedirectResponse(url="/admin/plugins", status_code=303)
