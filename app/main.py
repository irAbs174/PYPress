from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.cms.router import router as cms_router
from app.core.config import get_settings
from app.database.init_db import create_tables, seed_admin
from app.database.session import SessionLocal


BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    with SessionLocal() as session:
        seed_admin(session)
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
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    app.state.templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(cms_router)

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/admin", status_code=303)

    @app.exception_handler(401)
    async def handle_unauthorized(_: Request, __):
        return RedirectResponse(url="/login", status_code=303)

    return app


app = create_app()
