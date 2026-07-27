"""Maintenance Mode — lock the public site behind a configurable notice."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.cms.settings import get_setting, set_setting
from app.core.dependencies import require_roles
from app.core.security import ensure_csrf_token, validate_csrf
from app.database.session import get_db_session


SETTING_KEY = "maintenance_mode.config"
DEFAULTS = {
    "enabled": False,
    "title": "We'll be right back",
    "message": "PYpress is undergoing scheduled maintenance. Please check again soon.",
}


def load_config(session: Session) -> dict[str, Any]:
    raw = get_setting(session, SETTING_KEY, "")
    config = dict(DEFAULTS)
    if raw.strip():
        try:
            stored = json.loads(raw)
            if isinstance(stored, dict):
                config["enabled"] = bool(stored.get("enabled", False))
                config["title"] = str(stored.get("title") or DEFAULTS["title"])
                config["message"] = str(stored.get("message") or DEFAULTS["message"])
        except json.JSONDecodeError:
            pass
    return config


def save_config(session: Session, config: dict[str, Any]) -> None:
    set_setting(
        session,
        SETTING_KEY,
        json.dumps(
            {
                "enabled": bool(config.get("enabled")),
                "title": str(config.get("title") or DEFAULTS["title"]),
                "message": str(config.get("message") or DEFAULTS["message"]),
            }
        ),
    )


def maintenance_html(title: str, message: str) -> str:
    safe_title = (
        title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    safe_message = (
        message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    body {{
      margin: 0; min-height: 100vh; display: grid; place-items: center;
      font-family: system-ui, sans-serif; background: #0b0f19; color: #e2e8f0;
      padding: 2rem;
    }}
    main {{
      max-width: 32rem; text-align: center; background: #131927;
      border: 1px solid #1f293d; border-radius: 1rem; padding: 2.5rem;
    }}
    h1 {{ margin: 0 0 1rem; font-size: 1.75rem; }}
    p {{ margin: 0; color: #94a3b8; line-height: 1.6; }}
    a {{ color: #60a5fa; }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_title}</h1>
    <p>{safe_message}</p>
    <p style="margin-top:1.5rem;font-size:0.875rem;"><a href="/login">Admin sign in</a></p>
  </main>
</body>
</html>
"""


router = APIRouter(prefix="/admin/maintenance", tags=["maintenance-mode"])


@router.get("")
def settings_page(
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    config = load_config(session)
    return request.app.state.templates.TemplateResponse(
        request,
        "maintenance_mode/settings.html",
        {
            "current_user": user,
            "csrf_token": ensure_csrf_token(request),
            "config": config,
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("")
def save_settings(
    request: Request,
    csrf_token: Annotated[str, Form()],
    title: Annotated[str, Form()] = DEFAULTS["title"],
    message: Annotated[str, Form()] = DEFAULTS["message"],
    enabled: Annotated[str, Form()] = "",
    user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    save_config(
        session,
        {
            "enabled": enabled == "on",
            "title": title.strip() or DEFAULTS["title"],
            "message": message.strip() or DEFAULTS["message"],
        },
    )
    return RedirectResponse(url="/admin/maintenance?saved=1", status_code=303)


def register(app, hooks):
    from pathlib import Path

    from jinja2 import ChoiceLoader, FileSystemLoader

    plugin_templates = Path(__file__).resolve().parent / "templates"
    env = app.state.templates.env
    if plugin_templates.exists():
        existing = list(env.loader.loaders) if isinstance(env.loader, ChoiceLoader) else [env.loader]
        search = str(plugin_templates)
        already = any(getattr(loader, "searchpath", None) and search in loader.searchpath for loader in existing)
        if not already:
            env.loader = ChoiceLoader([*existing, FileSystemLoader(search)])

    if not getattr(app.state, "_maintenance_mode_routes", False):
        app.include_router(router)
        app.state._maintenance_mode_routes = True

    def add_nav(items: list[dict[str, Any]], request: Request):
        items = list(items or [])
        items.append(
            {
                "href": "/admin/maintenance",
                "label": "Maintenance",
                "icon": "fa-solid fa-road-barrier",
            }
        )
        return items

    def gate_public(response, request: Request, session: Session):
        if response is not None:
            return response
        config = load_config(session)
        if not config.get("enabled"):
            return None

        user_id = request.session.get("user_id")
        if user_id:
            user = session.get(User, user_id)
            if user and user.role in {
                UserRole.ADMIN.value,
                UserRole.EDITOR.value,
                UserRole.AUTHOR.value,
            }:
                return None

        return HTMLResponse(
            maintenance_html(config["title"], config["message"]),
            status_code=503,
            headers={"Retry-After": "3600"},
        )

    hooks.add_filter("admin.nav_items", add_nav)
    hooks.add_filter("public.access", gate_public)
