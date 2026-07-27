from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.cms.settings import get_enabled_plugins, set_enabled_plugins
from app.core.config import get_settings
from app.core.dependencies import require_roles
from app.core.security import ensure_csrf_token, validate_csrf
from app.database.session import get_db_session
from app.plugins import default_enabled_plugins, discover_plugins
from app.plugins.hooks import HookRegistry
from app.plugins.manager import (
    STARTER_PLUGIN_PY,
    create_plugin,
    delete_plugin,
    install_plugin_from_zip,
    read_plugin_files,
    reload_plugins,
    update_plugin,
    validate_plugin_name,
)


router = APIRouter(prefix="/admin/plugins", tags=["plugins"])


def _reload(request: Request, session: Session) -> None:
    enabled = get_enabled_plugins(session, defaults=default_enabled_plugins())
    hooks: HookRegistry = request.app.state.hooks
    reload_plugins(request.app, hooks, enabled)


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
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
        },
    )


@router.get("/new")
def new_plugin_form(
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
):
    return request.app.state.templates.TemplateResponse(
        request,
        "plugins/edit.html",
        {
            "current_user": user,
            "csrf_token": ensure_csrf_token(request),
            "is_new": True,
            "name": "",
            "version": "0.1.0",
            "description": "",
            "enabled_by_default": False,
            "source": STARTER_PLUGIN_PY.format(name="my_plugin"),
            "error": None,
            "message": None,
        },
    )


@router.post("/new")
def create_plugin_action(
    request: Request,
    name: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    version: Annotated[str, Form()] = "0.1.0",
    description: Annotated[str, Form()] = "",
    source: Annotated[str, Form()] = "",
    enabled_by_default: Annotated[str, Form()] = "",
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    try:
        plugin = create_plugin(
            name,
            version=version,
            description=description,
            source=source or None,
            enabled_by_default=enabled_by_default == "on",
        )
        enabled = get_enabled_plugins(session, defaults=default_enabled_plugins())
        enabled.add(plugin.name)
        set_enabled_plugins(session, sorted(enabled))
        _reload(request, session)
    except (ValueError, FileExistsError) as exc:
        return request.app.state.templates.TemplateResponse(
            request,
            "plugins/edit.html",
            {
                "current_user": user,
                "csrf_token": ensure_csrf_token(request),
                "is_new": True,
                "name": name,
                "version": version,
                "description": description,
                "enabled_by_default": enabled_by_default == "on",
                "source": source or STARTER_PLUGIN_PY.format(name="my_plugin"),
                "error": str(exc),
                "message": None,
            },
            status_code=400,
        )
    return RedirectResponse(url=f"/admin/plugins/{plugin.name}/edit?message=created", status_code=303)


@router.post("/upload")
async def upload_plugin(
    request: Request,
    csrf_token: Annotated[str, Form()],
    file: UploadFile = File(...),
    overwrite: Annotated[str, Form()] = "",
    enable: Annotated[str, Form()] = "on",
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        return RedirectResponse(url="/admin/plugins?error=ZIP+file+too+large", status_code=303)

    filename = (file.filename or "").lower()
    if not filename.endswith(".zip"):
        return RedirectResponse(url="/admin/plugins?error=Only+.zip+uploads+are+supported", status_code=303)

    try:
        plugin = install_plugin_from_zip(data, overwrite=overwrite == "on")
        if enable == "on":
            enabled = get_enabled_plugins(session, defaults=default_enabled_plugins())
            enabled.add(plugin.name)
            set_enabled_plugins(session, sorted(enabled))
        _reload(request, session)
    except (ValueError, FileExistsError) as exc:
        return RedirectResponse(url=f"/admin/plugins?error={quote(str(exc))}", status_code=303)

    return RedirectResponse(url=f"/admin/plugins/{plugin.name}/edit?message=uploaded", status_code=303)


@router.post("/toggle")
def toggle_plugin(
    request: Request,
    plugin_name: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
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
    _reload(request, session)
    return RedirectResponse(url="/admin/plugins", status_code=303)


@router.get("/{plugin_name}/edit")
def edit_plugin_form(
    plugin_name: str,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
):
    try:
        name = validate_plugin_name(plugin_name)
        manifest, source = read_plugin_files(name)
    except (ValueError, FileNotFoundError) as exc:
        return RedirectResponse(url=f"/admin/plugins?error={quote(str(exc))}", status_code=303)

    return request.app.state.templates.TemplateResponse(
        request,
        "plugins/edit.html",
        {
            "current_user": user,
            "csrf_token": ensure_csrf_token(request),
            "is_new": False,
            "name": name,
            "version": manifest.get("version", "0.1.0"),
            "description": manifest.get("description", ""),
            "enabled_by_default": bool(manifest.get("enabled_by_default", False)),
            "source": source,
            "error": None,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/{plugin_name}/edit")
def edit_plugin_action(
    plugin_name: str,
    request: Request,
    csrf_token: Annotated[str, Form()],
    version: Annotated[str, Form()] = "0.1.0",
    description: Annotated[str, Form()] = "",
    source: Annotated[str, Form()] = "",
    enabled_by_default: Annotated[str, Form()] = "",
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    try:
        name = validate_plugin_name(plugin_name)
        update_plugin(
            name,
            version=version,
            description=description,
            source=source,
            enabled_by_default=enabled_by_default == "on",
        )
        _reload(request, session)
    except (ValueError, FileNotFoundError) as exc:
        return request.app.state.templates.TemplateResponse(
            request,
            "plugins/edit.html",
            {
                "current_user": user,
                "csrf_token": ensure_csrf_token(request),
                "is_new": False,
                "name": plugin_name,
                "version": version,
                "description": description,
                "enabled_by_default": enabled_by_default == "on",
                "source": source,
                "error": str(exc),
                "message": None,
            },
            status_code=400,
        )
    return RedirectResponse(url=f"/admin/plugins/{name}/edit?message=saved", status_code=303)


@router.post("/{plugin_name}/delete")
def delete_plugin_action(
    plugin_name: str,
    request: Request,
    csrf_token: Annotated[str, Form()],
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    try:
        name = validate_plugin_name(plugin_name)
        delete_plugin(name)
        enabled = get_enabled_plugins(session, defaults=default_enabled_plugins())
        enabled.discard(name)
        set_enabled_plugins(session, sorted(enabled))
        _reload(request, session)
    except (ValueError, FileNotFoundError) as exc:
        return RedirectResponse(url=f"/admin/plugins?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(url="/admin/plugins?message=deleted", status_code=303)
