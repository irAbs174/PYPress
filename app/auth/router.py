from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.core.security import (
    ensure_csrf_token,
    hash_password,
    validate_csrf,
    verify_password,
)
from app.database.session import get_db_session


router = APIRouter(tags=["auth"])


def render_login(request: Request, error: str | None = None):
    return request.app.state.templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "error": error,
            "csrf_token": ensure_csrf_token(request),
            "current_user": None,
        },
        status_code=200 if error is None else 400,
    )


def render_register(request: Request, error: str | None = None, email: str = ""):
    return request.app.state.templates.TemplateResponse(
        request,
        "auth/register.html",
        {
            "error": error,
            "email": email,
            "csrf_token": ensure_csrf_token(request),
            "current_user": None,
        },
        status_code=200 if error is None else 400,
    )


@router.get("/login")
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/admin", status_code=303)
    return render_login(request)


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        return render_login(request, error="Invalid email or password.")

    request.session.clear()
    request.session["user_id"] = user.id
    ensure_csrf_token(request)
    if user.role == UserRole.SUBSCRIBER.value:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/register")
def register_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
    return render_register(request)


@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    csrf_token: str = Form(...),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    email = email.strip().lower()
    password = password.strip()
    password_confirm = password_confirm.strip()

    if not email or not password:
        return render_register(request, error="Email and password are required.", email=email)
    if len(password) < 8:
        return render_register(
            request,
            error="Password must be at least 8 characters.",
            email=email,
        )
    if password != password_confirm:
        return render_register(request, error="Passwords do not match.", email=email)

    existing = session.scalar(select(User).where(User.email == email))
    if existing:
        return render_register(request, error="An account with that email already exists.", email=email)

    user = User(
        email=email,
        password_hash=hash_password(password),
        role=UserRole.SUBSCRIBER.value,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    request.session.clear()
    request.session["user_id"] = user.id
    ensure_csrf_token(request)
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse(url=f"/login?logged_out={quote('1')}", status_code=303)
