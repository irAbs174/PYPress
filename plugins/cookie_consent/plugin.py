"""Cookie Consent — lightweight GDPR-style notice for the public site."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.cms.settings import get_setting, set_setting
from app.core.dependencies import require_roles
from app.core.security import ensure_csrf_token, validate_csrf
from app.database.session import get_db_session


SETTING_KEY = "cookie_consent.config"
DEFAULTS = {
    "message": "We use cookies to improve your experience on this site.",
    "button_label": "Got it",
    "policy_url": "",
}


def load_config(session: Session) -> dict[str, str]:
    raw = get_setting(session, SETTING_KEY, "")
    config = dict(DEFAULTS)
    if raw.strip():
        try:
            stored = json.loads(raw)
            if isinstance(stored, dict):
                for key in DEFAULTS:
                    if key in stored and stored[key] is not None:
                        config[key] = str(stored[key])
        except json.JSONDecodeError:
            pass
    return config


def save_config(session: Session, config: dict[str, str]) -> None:
    set_setting(session, SETTING_KEY, json.dumps({key: (config.get(key) or DEFAULTS[key]) for key in DEFAULTS}))


def banner_html(config: dict[str, str]) -> str:
    policy = ""
    if config.get("policy_url"):
        href = config["policy_url"].replace('"', "&quot;")
        policy = f' <a href="{href}" style="color:#93c5fd;text-decoration:underline;">Privacy policy</a>'
    message = (
        config["message"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    label = (
        config["button_label"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"""
<div id="pypress-cookie-banner" style="position:fixed;bottom:1rem;left:1rem;right:1rem;z-index:60;max-width:40rem;margin:0 auto;background:#131927;border:1px solid #1f293d;border-radius:0.75rem;padding:1rem 1.25rem;display:none;align-items:center;justify-content:space-between;gap:1rem;box-shadow:0 10px 40px rgba(0,0,0,.35);">
  <p style="margin:0;color:#cbd5e1;font-size:0.9rem;line-height:1.5;">{message}{policy}</p>
  <button type="button" id="pypress-cookie-accept" style="flex-shrink:0;background:#2563eb;color:#fff;border:0;border-radius:0.5rem;padding:0.55rem 0.9rem;cursor:pointer;font:inherit;">{label}</button>
</div>
<script>
(function () {{
  try {{
    if (localStorage.getItem("pypress_cookie_ok") === "1") return;
  }} catch (e) {{}}
  var banner = document.getElementById("pypress-cookie-banner");
  var btn = document.getElementById("pypress-cookie-accept");
  if (!banner || !btn) return;
  banner.style.display = "flex";
  btn.addEventListener("click", function () {{
    try {{ localStorage.setItem("pypress_cookie_ok", "1"); }} catch (e) {{}}
    banner.remove();
  }});
}})();
</script>
"""


router = APIRouter(prefix="/admin/cookie-consent", tags=["cookie-consent"])


@router.get("")
def settings_page(
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    return request.app.state.templates.TemplateResponse(
        request,
        "cookie_consent/settings.html",
        {
            "current_user": user,
            "csrf_token": ensure_csrf_token(request),
            "config": load_config(session),
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("")
def save_settings(
    request: Request,
    csrf_token: Annotated[str, Form()],
    message: Annotated[str, Form()] = DEFAULTS["message"],
    button_label: Annotated[str, Form()] = DEFAULTS["button_label"],
    policy_url: Annotated[str, Form()] = "",
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    save_config(
        session,
        {
            "message": message.strip() or DEFAULTS["message"],
            "button_label": button_label.strip() or DEFAULTS["button_label"],
            "policy_url": policy_url.strip(),
        },
    )
    return RedirectResponse(url="/admin/cookie-consent?saved=1", status_code=303)


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

    if not getattr(app.state, "_cookie_consent_routes", False):
        app.include_router(router)
        app.state._cookie_consent_routes = True

    def add_nav(items: list[dict[str, Any]], request: Request):
        items = list(items or [])
        items.append(
            {
                "href": "/admin/cookie-consent",
                "label": "Cookie banner",
                "icon": "fa-solid fa-cookie-bite",
            }
        )
        return items

    def inject_banner(context: dict, request: Request):
        context = dict(context)
        from app.database.session import SessionLocal

        with SessionLocal() as session:
            config = load_config(session)
        context["plugin_body_html"] = (context.get("plugin_body_html") or "") + banner_html(config)
        return context

    hooks.add_filter("admin.nav_items", add_nav)
    hooks.add_filter("public.before_render", inject_banner)
