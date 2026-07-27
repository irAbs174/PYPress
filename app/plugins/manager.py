from __future__ import annotations

import ast
import io
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

from fastapi import FastAPI

from app.plugins import PluginInfo, discover_plugins, load_plugins, plugins_root
from app.plugins.hooks import HookRegistry


PLUGIN_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")

STARTER_PLUGIN_PY = '''def register(app, hooks):
    """Register this plugin with the PYpress hook system."""

    def add_footer_note(context, request):
        context = dict(context)
        context["plugin_footer_note"] = "Hello from {name}."
        return context

    hooks.add_filter("public.before_render", add_footer_note)
'''


def validate_plugin_name(name: str) -> str:
    cleaned = name.strip().lower().replace("-", "_").replace(" ", "_")
    if not PLUGIN_NAME_RE.match(cleaned):
        raise ValueError(
            "Plugin name must be lowercase, start with a letter, and use only letters, numbers, or underscores."
        )
    return cleaned


def validate_python_source(source: str) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"Invalid Python syntax: {exc.msg} (line {exc.lineno})") from exc

    has_register = any(
        isinstance(node, ast.FunctionDef) and node.name == "register" for node in tree.body
    )
    if not has_register:
        raise ValueError("plugin.py must define a register(app, hooks) function.")


def plugin_dir(name: str) -> Path:
    return plugins_root() / name


def read_plugin_files(name: str) -> tuple[dict, str]:
    path = plugin_dir(name)
    manifest_path = path / "plugin.json"
    source_path = path / "plugin.py"
    if not manifest_path.exists() or not source_path.exists():
        raise FileNotFoundError(f"Plugin '{name}' not found.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = source_path.read_text(encoding="utf-8")
    return manifest, source


def write_plugin_files(
    name: str,
    *,
    version: str,
    description: str,
    source: str,
    enabled_by_default: bool = False,
    overwrite: bool = False,
) -> PluginInfo:
    name = validate_plugin_name(name)
    validate_python_source(source)

    root = plugins_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    if path.exists() and not overwrite:
        raise FileExistsError(f"Plugin '{name}' already exists.")
    path.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": name,
        "version": (version.strip() or "0.1.0"),
        "description": description.strip(),
        "enabled_by_default": bool(enabled_by_default),
    }
    (path / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (path / "plugin.py").write_text(source if source.endswith("\n") else source + "\n", encoding="utf-8")
    return PluginInfo(
        name=name,
        version=manifest["version"],
        description=manifest["description"],
        path=path,
        enabled_by_default=manifest["enabled_by_default"],
    )


def create_plugin(
    name: str,
    *,
    version: str = "0.1.0",
    description: str = "",
    source: str | None = None,
    enabled_by_default: bool = False,
) -> PluginInfo:
    name = validate_plugin_name(name)
    if source is None:
        source = STARTER_PLUGIN_PY.format(name=name)
    return write_plugin_files(
        name,
        version=version,
        description=description,
        source=source,
        enabled_by_default=enabled_by_default,
        overwrite=False,
    )


def update_plugin(
    name: str,
    *,
    version: str,
    description: str,
    source: str,
    enabled_by_default: bool = False,
) -> PluginInfo:
    name = validate_plugin_name(name)
    if not plugin_dir(name).exists():
        raise FileNotFoundError(f"Plugin '{name}' not found.")
    return write_plugin_files(
        name,
        version=version,
        description=description,
        source=source,
        enabled_by_default=enabled_by_default,
        overwrite=True,
    )


def delete_plugin(name: str) -> None:
    name = validate_plugin_name(name)
    path = plugin_dir(name)
    if not path.exists():
        raise FileNotFoundError(f"Plugin '{name}' not found.")
    shutil.rmtree(path)
    module_name = f"pypress_plugin_{name}"
    sys.modules.pop(module_name, None)


def _safe_extract_member(zf: zipfile.ZipFile, member: zipfile.ZipInfo, dest: Path) -> None:
    target = (dest / member.filename).resolve()
    if not str(target).startswith(str(dest.resolve())):
        raise ValueError("ZIP contains an unsafe path.")
    if member.is_dir() or member.filename.endswith("/"):
        target.mkdir(parents=True, exist_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member, "r") as src, open(target, "wb") as out:
        shutil.copyfileobj(src, out)


def install_plugin_from_zip(data: bytes, *, overwrite: bool = False) -> PluginInfo:
    if not data:
        raise ValueError("Empty upload.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded file is not a valid ZIP archive.") from exc

    names = [n for n in zf.namelist() if n and not n.startswith("__MACOSX/") and not n.endswith(".DS_Store")]
    if not names:
        raise ValueError("ZIP archive is empty.")

    top_dirs = sorted({n.split("/")[0] for n in names if "/" in n})

    extract_root = plugins_root() / "_tmp_upload"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    try:
        for info in zf.infolist():
            if info.filename.startswith("__MACOSX/") or info.filename.endswith(".DS_Store"):
                continue
            _safe_extract_member(zf, info, extract_root)

        candidate: Path | None = None
        if (extract_root / "plugin.json").exists() and (extract_root / "plugin.py").exists():
            candidate = extract_root
        elif len(top_dirs) == 1:
            nested = extract_root / top_dirs[0]
            if (nested / "plugin.json").exists() and (nested / "plugin.py").exists():
                candidate = nested
        else:
            # Multiple top-level dirs: find first valid plugin folder
            for entry in sorted(extract_root.iterdir()):
                if entry.is_dir() and (entry / "plugin.json").exists() and (entry / "plugin.py").exists():
                    candidate = entry
                    break

        if candidate is None:
            raise ValueError("ZIP must contain plugin.json and plugin.py (at root or in one folder).")

        manifest = json.loads((candidate / "plugin.json").read_text(encoding="utf-8"))
        name = validate_plugin_name(str(manifest.get("name") or candidate.name))
        source = (candidate / "plugin.py").read_text(encoding="utf-8")
        validate_python_source(source)

        dest = plugin_dir(name)
        if dest.exists():
            if not overwrite:
                raise FileExistsError(f"Plugin '{name}' already exists. Enable overwrite to replace it.")
            shutil.rmtree(dest)

        shutil.copytree(candidate, dest)
        # Normalize manifest name to folder name
        manifest["name"] = name
        (dest / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return PluginInfo(
            name=name,
            version=str(manifest.get("version", "0.0.0")),
            description=str(manifest.get("description", "")),
            path=dest,
            enabled_by_default=bool(manifest.get("enabled_by_default", False)),
        )
    finally:
        if extract_root.exists():
            shutil.rmtree(extract_root, ignore_errors=True)
        zf.close()


def reload_plugins(app: FastAPI, hooks: HookRegistry, enabled_names: set[str]) -> list[str]:
    for name in list(sys.modules):
        if name.startswith("pypress_plugin_"):
            sys.modules.pop(name, None)
    hooks.clear()
    loaded = load_plugins(app, hooks, enabled_names)
    app.state.loaded_plugins = loaded
    hooks.do_action("app.startup", app)
    return loaded
