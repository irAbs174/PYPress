from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.admin.router import router as admin_router
from app.api.router import router as api_router
from app.auth.router import router as auth_router
from app.auth.users_router import router as users_router
from app.cms.public_router import router as public_router
from app.cms.router import router as cms_router
from app.cms.router import taxonomy_router
from app.cms.settings import get_enabled_plugins, get_setting
from app.core.config import get_settings
from app.database.init_db import create_tables, seed_admin, seed_defaults
from app.database.session import SessionLocal
from app.media import ensure_upload_dir
from app.media import router as media_router
from app.plugins import default_enabled_plugins, load_plugins
from app.plugins.hooks import HookRegistry
from app.plugins.router import router as plugins_router
from app.themes import build_templates
from app.themes.router import router as themes_router


BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    ensure_upload_dir()
    with SessionLocal() as session:
        seed_admin(session)
        seed_defaults(session)
        active_theme = get_setting(session, "active_theme", settings.default_theme)
        enabled_plugins = get_enabled_plugins(session, defaults=default_enabled_plugins())

    app.state.templates = build_templates(active_theme)
    app.state.active_theme = active_theme
    app.state.hooks = HookRegistry()
    load_plugins(app, app.state.hooks, enabled_plugins)
    app.state.hooks.do_action("app.startup", app)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie=settings.session_cookie_name,
        same_site="lax",
        https_only=False,
    )

    upload_dir = ensure_upload_dir()
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")

    themes_dir = Path(settings.themes_dir)
    if themes_dir.exists():
        # Per-theme static is served from active theme path via a small helper mount below.
        pass

    app.include_router(public_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(cms_router)
    app.include_router(taxonomy_router)
    app.include_router(media_router)
    app.include_router(themes_router)
    app.include_router(plugins_router)
    app.include_router(users_router)
    app.include_router(api_router)

    @app.get("/theme-static/{file_path:path}", include_in_schema=False)
    def theme_static(file_path: str, request: Request):
        from fastapi import HTTPException
        from fastapi.responses import FileResponse

        theme_name = getattr(request.app.state, "active_theme", settings.default_theme)
        candidate = (Path(settings.themes_dir) / theme_name / "static" / file_path).resolve()
        static_root = (Path(settings.themes_dir) / theme_name / "static").resolve()
        if not str(candidate).startswith(str(static_root)) or not candidate.is_file():
            raise HTTPException(status_code=404, detail="Theme asset not found.")
        return FileResponse(candidate)

    @app.exception_handler(401)
    async def handle_unauthorized(request: Request, __):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Authentication required."}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)

    return app


app = create_app()
