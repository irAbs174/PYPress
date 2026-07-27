from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.core.config import get_settings
from app.plugins.hooks import HookRegistry


@dataclass
class PluginInfo:
    name: str
    version: str
    description: str
    path: Path
    enabled_by_default: bool = False


def plugins_root() -> Path:
    return Path(get_settings().plugins_dir)


def discover_plugins() -> list[PluginInfo]:
    root = plugins_root()
    if not root.exists():
        return []

    plugins: list[PluginInfo] = []
    for entry in sorted(root.iterdir()):
        manifest = entry / "plugin.json"
        if not entry.is_dir() or not manifest.exists():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        plugins.append(
            PluginInfo(
                name=data.get("name", entry.name),
                version=data.get("version", "0.0.0"),
                description=data.get("description", ""),
                path=entry,
                enabled_by_default=bool(data.get("enabled_by_default", False)),
            )
        )
    return plugins


def _load_module(plugin: PluginInfo):
    module_path = plugin.path / "plugin.py"
    if not module_path.exists():
        return None
    module_name = f"pypress_plugin_{plugin.name}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_plugins(app: FastAPI, hooks: HookRegistry, enabled_names: set[str] | None = None) -> list[str]:
    loaded: list[str] = []
    discovered = {plugin.name: plugin for plugin in discover_plugins()}

    if enabled_names is None:
        enabled_names = {
            name for name, plugin in discovered.items() if plugin.enabled_by_default
        }

    for name in sorted(enabled_names):
        plugin = discovered.get(name)
        if plugin is None:
            continue
        module = _load_module(plugin)
        if module is None or not hasattr(module, "register"):
            continue
        module.register(app, hooks)
        loaded.append(name)

    app.state.loaded_plugins = loaded
    return loaded


def default_enabled_plugins() -> set[str]:
    return {plugin.name for plugin in discover_plugins() if plugin.enabled_by_default}
