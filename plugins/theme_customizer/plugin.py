"""Theme Customizer — Elementor-inspired appearance settings for the public site.

Registers an admin settings page under Appearance and injects colors, hero
copy, fonts, and custom CSS into public templates via hooks.
"""

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


SETTING_KEY = "theme_customizer.config"

DEFAULTS: dict[str, str] = {
    "primary_color": "#3b82f6",
    "accent_color": "#22d3ee",
    "background_color": "#0b0f19",
    "card_color": "#131927",
    "text_color": "#f1f5f9",
    "font_family": "Plus Jakarta Sans",
    "hero_title": "",
    "hero_subtitle": "",
    "hero_cta_text": "",
    "hero_cta_url": "",
    "hero_handwritten": "",
    "custom_css": "",
}

PRESETS = {
    "ocean": {
        "primary_color": "#0ea5e9",
        "accent_color": "#2dd4bf",
        "background_color": "#0b1220",
        "card_color": "#111827",
        "text_color": "#e2e8f0",
        "font_family": "Plus Jakarta Sans",
    },
    "sunset": {
        "primary_color": "#f97316",
        "accent_color": "#fb7185",
        "background_color": "#140d0a",
        "card_color": "#1c1210",
        "text_color": "#fff7ed",
        "font_family": "Plus Jakarta Sans",
    },
    "forest": {
        "primary_color": "#22c55e",
        "accent_color": "#a3e635",
        "background_color": "#0a120e",
        "card_color": "#102017",
        "text_color": "#ecfdf5",
        "font_family": "Plus Jakarta Sans",
    },
    "violet": {
        "primary_color": "#8b5cf6",
        "accent_color": "#e879f9",
        "background_color": "#0f0a1a",
        "card_color": "#1a1027",
        "text_color": "#f5f3ff",
        "font_family": "Plus Jakarta Sans",
    },
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
    cleaned = {key: (config.get(key) or DEFAULTS[key]).strip() for key in DEFAULTS}
    set_setting(session, SETTING_KEY, json.dumps(cleaned))


def css_vars(config: dict[str, str]) -> str:
    return "\n".join(
        [
            f"--brand-500: {config['primary_color']};",
            f"--brand-600: {config['primary_color']};",
            f"--accent: {config['accent_color']};",
            f"--dark-bg: {config['background_color']};",
            f"--dark-card: {config['card_color']};",
            f"--text-main: {config['text_color']};",
        ]
    )


def generated_css(config: dict[str, str]) -> str:
    font = config["font_family"].replace("'", "")
    return f"""
body, .font-sans {{
  font-family: '{font}', system-ui, sans-serif !important;
  color: var(--text-main, {config['text_color']});
}}
.bg-dark-bg {{ background-color: var(--dark-bg, {config['background_color']}) !important; }}
.bg-dark-card, footer.bg-dark-card\\/50 {{ background-color: var(--dark-card, {config['card_color']}) !important; }}
.bg-brand-600, .bg-brand-500, a.bg-brand-600 {{ background-color: var(--brand-600, {config['primary_color']}) !important; }}
.text-brand-500, .text-brand-600 {{ color: var(--brand-500, {config['primary_color']}) !important; }}
.shadow-brand-500\\/20, .shadow-brand-500\\/25 {{ --tw-shadow-color: {config['primary_color']}40; }}
.font-hand {{ color: var(--accent, {config['accent_color']}) !important; }}
.selection\\:bg-brand-500::selection {{ background-color: {config['primary_color']}; }}
"""


router = APIRouter(prefix="/admin/appearance", tags=["theme-customizer"])


@router.get("")
def appearance_page(
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    config = load_config(session)
    return request.app.state.templates.TemplateResponse(
        request,
        "theme_customizer/settings.html",
        {
            "current_user": user,
            "csrf_token": ensure_csrf_token(request),
            "config": config,
            "presets": list(PRESETS.keys()),
            "saved": request.query_params.get("saved") == "1",
            "error": None,
        },
    )


@router.post("")
def save_appearance(
    request: Request,
    csrf_token: Annotated[str, Form()],
    primary_color: Annotated[str, Form()] = DEFAULTS["primary_color"],
    accent_color: Annotated[str, Form()] = DEFAULTS["accent_color"],
    background_color: Annotated[str, Form()] = DEFAULTS["background_color"],
    card_color: Annotated[str, Form()] = DEFAULTS["card_color"],
    text_color: Annotated[str, Form()] = DEFAULTS["text_color"],
    font_family: Annotated[str, Form()] = DEFAULTS["font_family"],
    hero_title: Annotated[str, Form()] = "",
    hero_subtitle: Annotated[str, Form()] = "",
    hero_cta_text: Annotated[str, Form()] = "",
    hero_cta_url: Annotated[str, Form()] = "",
    hero_handwritten: Annotated[str, Form()] = "",
    custom_css: Annotated[str, Form()] = "",
    preset: Annotated[str, Form()] = "",
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    config = {
        "primary_color": primary_color,
        "accent_color": accent_color,
        "background_color": background_color,
        "card_color": card_color,
        "text_color": text_color,
        "font_family": font_family,
        "hero_title": hero_title,
        "hero_subtitle": hero_subtitle,
        "hero_cta_text": hero_cta_text,
        "hero_cta_url": hero_cta_url,
        "hero_handwritten": hero_handwritten,
        "custom_css": custom_css,
    }
    if preset in PRESETS:
        config.update(PRESETS[preset])
    save_config(session, config)
    return RedirectResponse(url="/admin/appearance?saved=1", status_code=303)


@router.post("/reset")
def reset_appearance(
    request: Request,
    csrf_token: Annotated[str, Form()],
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    save_config(session, dict(DEFAULTS))
    return RedirectResponse(url="/admin/appearance?saved=1", status_code=303)


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

    if not getattr(app.state, "_theme_customizer_routes", False):
        app.include_router(router)
        app.state._theme_customizer_routes = True

    def add_nav(items: list[dict[str, Any]], request: Request):
        items = list(items or [])
        items.append(
            {
                "href": "/admin/appearance",
                "label": "Appearance",
                "icon": "fa-solid fa-palette",
            }
        )
        return items

    def inject_theme(context: dict, request: Request):
        context = dict(context)
        from app.database.session import SessionLocal

        with SessionLocal() as session:
            config = load_config(session)

        context["theme_custom_css_vars"] = css_vars(config)
        context["theme_custom_css"] = generated_css(config) + "\n" + (config.get("custom_css") or "")
        context["theme_body_style"] = f"background-color: {config['background_color']};"
        context["custom_hero_title"] = config.get("hero_title") or None
        context["custom_hero_subtitle"] = config.get("hero_subtitle") or None
        context["custom_hero_cta_text"] = config.get("hero_cta_text") or None
        context["custom_hero_cta_url"] = config.get("hero_cta_url") or None
        context["custom_hero_handwritten"] = config.get("hero_handwritten") or None

        font = config["font_family"].replace(" ", "+")
        context["plugin_head_html"] = (
            (context.get("plugin_head_html") or "")
            + f'<link href="https://fonts.googleapis.com/css2?family={font}:wght@400;500;600;700;800&display=swap" rel="stylesheet" />'
        )
        return context

    hooks.add_filter("admin.nav_items", add_nav)
    hooks.add_filter("public.before_render", inject_theme)
