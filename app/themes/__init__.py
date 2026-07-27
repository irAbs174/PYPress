from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

from app.core.config import BASE_DIR, get_settings


@dataclass
class ThemeInfo:
    name: str
    version: str
    description: str
    path: Path


def themes_root() -> Path:
    return Path(get_settings().themes_dir)


def discover_themes() -> list[ThemeInfo]:
    root = themes_root()
    if not root.exists():
        return []

    themes: list[ThemeInfo] = []
    for entry in sorted(root.iterdir()):
        manifest = entry / "theme.json"
        if not entry.is_dir() or not manifest.exists():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        themes.append(
            ThemeInfo(
                name=data.get("name", entry.name),
                version=data.get("version", "0.0.0"),
                description=data.get("description", ""),
                path=entry,
            )
        )
    return themes


def get_theme_path(theme_name: str) -> Path | None:
    path = themes_root() / theme_name
    if path.is_dir() and (path / "theme.json").exists():
        return path
    return None


def build_templates(active_theme: str | None = None) -> Jinja2Templates:
    settings = get_settings()
    theme_name = active_theme or settings.default_theme
    loaders = []

    theme_path = get_theme_path(theme_name)
    if theme_path is None:
        theme_path = get_theme_path(settings.default_theme)

    if theme_path is not None:
        theme_templates = theme_path / "templates"
        if theme_templates.exists():
            loaders.append(FileSystemLoader(str(theme_templates)))

    admin_templates = BASE_DIR / "app" / "templates"
    loaders.append(FileSystemLoader(str(admin_templates)))

    templates = Jinja2Templates(directory=str(admin_templates))
    templates.env.loader = ChoiceLoader(loaders)

    def plugin_context(request):
        hooks = getattr(request.app.state, "hooks", None)
        nav_items = []
        if hooks is not None:
            nav_items = hooks.apply_filters("admin.nav_items", [], request) or []
        return {"plugin_nav_items": nav_items}

    templates.context_processors.append(plugin_context)
    return templates
