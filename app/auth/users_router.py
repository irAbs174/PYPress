from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.core.dependencies import require_roles
from app.core.security import ensure_csrf_token, hash_password, validate_csrf
from app.database.session import get_db_session


router = APIRouter(prefix="/admin/users", tags=["users"])

EDITABLE_ROLES = {
    UserRole.ADMIN.value,
    UserRole.EDITOR.value,
    UserRole.AUTHOR.value,
    UserRole.SUBSCRIBER.value,
}


def users_context(
    request: Request,
    current_user: User,
    users: list[User],
    *,
    error: str | None = None,
    edit_user: User | None = None,
) -> dict[str, Any]:
    return {
        "current_user": current_user,
        "csrf_token": ensure_csrf_token(request),
        "users": users,
        "edit_user": edit_user,
        "roles": sorted(EDITABLE_ROLES),
        "error": error,
    }


@router.get("")
def list_users(
    request: Request,
    current_user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    users = session.scalars(select(User).order_by(User.created_at.desc())).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "users/list.html",
        users_context(request, current_user, users),
    )


@router.post("")
def create_user(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    current_user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    users = session.scalars(select(User).order_by(User.created_at.desc())).all()
    email = email.strip().lower()
    password = password.strip()
    if not email or not password:
        return request.app.state.templates.TemplateResponse(
            request,
            "users/list.html",
            users_context(request, current_user, users, error="Email and password are required."),
            status_code=400,
        )
    if len(password) < 8:
        return request.app.state.templates.TemplateResponse(
            request,
            "users/list.html",
            users_context(request, current_user, users, error="Password must be at least 8 characters."),
            status_code=400,
        )
    if role not in EDITABLE_ROLES:
        return request.app.state.templates.TemplateResponse(
            request,
            "users/list.html",
            users_context(request, current_user, users, error="Invalid role."),
            status_code=400,
        )
    existing = session.scalar(select(User).where(User.email == email))
    if existing:
        return request.app.state.templates.TemplateResponse(
            request,
            "users/list.html",
            users_context(request, current_user, users, error="A user with that email already exists."),
            status_code=400,
        )

    session.add(User(email=email, password_hash=hash_password(password), role=role))
    session.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/{user_id}/edit")
def edit_user_form(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    edit_user = session.get(User, user_id)
    if edit_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    users = session.scalars(select(User).order_by(User.created_at.desc())).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "users/list.html",
        users_context(request, current_user, users, edit_user=edit_user),
    )


@router.post("/{user_id}")
def update_user(
    user_id: int,
    request: Request,
    email: Annotated[str, Form()],
    role: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    password: Annotated[str, Form()] = "",
    current_user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    edit_user = session.get(User, user_id)
    if edit_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    users = session.scalars(select(User).order_by(User.created_at.desc())).all()
    email = email.strip().lower()
    password = password.strip()

    if not email:
        return request.app.state.templates.TemplateResponse(
            request,
            "users/list.html",
            users_context(request, current_user, users, edit_user=edit_user, error="Email is required."),
            status_code=400,
        )
    if role not in EDITABLE_ROLES:
        return request.app.state.templates.TemplateResponse(
            request,
            "users/list.html",
            users_context(request, current_user, users, edit_user=edit_user, error="Invalid role."),
            status_code=400,
        )
    if password and len(password) < 8:
        return request.app.state.templates.TemplateResponse(
            request,
            "users/list.html",
            users_context(
                request,
                current_user,
                users,
                edit_user=edit_user,
                error="Password must be at least 8 characters.",
            ),
            status_code=400,
        )

    duplicate = session.scalar(select(User).where(User.email == email, User.id != user_id))
    if duplicate:
        return request.app.state.templates.TemplateResponse(
            request,
            "users/list.html",
            users_context(
                request,
                current_user,
                users,
                edit_user=edit_user,
                error="A user with that email already exists.",
            ),
            status_code=400,
        )

    if edit_user.id == current_user.id and role != UserRole.ADMIN.value:
        return request.app.state.templates.TemplateResponse(
            request,
            "users/list.html",
            users_context(
                request,
                current_user,
                users,
                edit_user=edit_user,
                error="You cannot remove your own admin role.",
            ),
            status_code=400,
        )

    edit_user.email = email
    edit_user.role = role
    if password:
        edit_user.password_hash = hash_password(password)
    session.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/{user_id}/delete")
def delete_user(
    user_id: int,
    request: Request,
    csrf_token: Annotated[str, Form()],
    current_user: User = Depends(require_roles(UserRole.ADMIN.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    if user_id == current_user.id:
        users = session.scalars(select(User).order_by(User.created_at.desc())).all()
        return request.app.state.templates.TemplateResponse(
            request,
            "users/list.html",
            users_context(request, current_user, users, error="You cannot delete your own account."),
            status_code=400,
        )
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    session.delete(user)
    session.commit()
    return RedirectResponse(url="/admin/users", status_code=303)
