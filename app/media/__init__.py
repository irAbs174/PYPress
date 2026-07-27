from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.cms.models import MediaAsset
from app.core.config import get_settings
from app.core.dependencies import require_roles
from app.core.security import ensure_csrf_token, validate_csrf
from app.database.session import get_db_session


router = APIRouter(prefix="/admin/media", tags=["media"])

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".pdf",
    ".txt",
    ".md",
    ".doc",
    ".docx",
    ".mp4",
    ".webm",
}


def ensure_upload_dir() -> Path:
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def safe_filename(original_name: str) -> str:
    stem = Path(original_name).stem
    suffix = Path(original_name).suffix.lower()
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-").lower() or "file"
    return f"{cleaned}-{uuid.uuid4().hex[:8]}{suffix}"


@router.get("")
def list_media(
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    assets = session.scalars(select(MediaAsset).order_by(MediaAsset.created_at.desc())).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "media/list.html",
        {
            "current_user": user,
            "csrf_token": ensure_csrf_token(request),
            "assets": assets,
            "error": None,
        },
    )


@router.get("/json")
def list_media_json(
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    assets = session.scalars(select(MediaAsset).order_by(MediaAsset.created_at.desc())).all()
    return [
        {
            "id": asset.id,
            "filename": asset.filename,
            "original_name": asset.original_name,
            "mime_type": asset.mime_type,
            "url": f"/uploads/{asset.filename}",
            "size": asset.size,
        }
        for asset in assets
    ]


@router.post("/upload")
async def upload_media(
    request: Request,
    csrf_token: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    settings = get_settings()
    original_name = file.filename or "upload.bin"
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        assets = session.scalars(select(MediaAsset).order_by(MediaAsset.created_at.desc())).all()
        return request.app.state.templates.TemplateResponse(
            request,
            "media/list.html",
            {
                "current_user": user,
                "csrf_token": ensure_csrf_token(request),
                "assets": assets,
                "error": f"File type {suffix or '(none)'} is not allowed.",
            },
            status_code=400,
        )

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large.")

    upload_dir = ensure_upload_dir()
    filename = safe_filename(original_name)
    dest = upload_dir / filename
    dest.write_bytes(data)

    asset = MediaAsset(
        filename=filename,
        original_name=original_name,
        mime_type=file.content_type or "application/octet-stream",
        size=len(data),
        path=str(dest),
        uploaded_by_id=user.id,
    )
    session.add(asset)
    session.commit()
    return RedirectResponse(url="/admin/media", status_code=303)


@router.post("/{asset_id}/delete")
def delete_media(
    asset_id: int,
    request: Request,
    csrf_token: str = Form(...),
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    asset = session.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found.")

    path = Path(asset.path)
    if path.exists():
        path.unlink()
    session.delete(asset)
    session.commit()
    return RedirectResponse(url="/admin/media", status_code=303)
