from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.models import User, UserRole
from app.cms.models import Category, ContentItem, ContentStatus, ContentType, Tag
from app.cms.visibility import normalize_status_and_publish_at, parse_publish_at
from app.core.dependencies import require_roles
from app.core.security import ensure_csrf_token, validate_csrf
from app.core.utils import slugify
from app.database.session import get_db_session
from app.plugins.hooks import HookRegistry


router = APIRouter(prefix="/admin/content", tags=["cms"])
taxonomy_router = APIRouter(prefix="/admin/taxonomies", tags=["taxonomies"])


def list_context(
    request: Request,
    user: User,
    content_type: str,
    items: list[ContentItem],
) -> dict[str, Any]:
    return {
        "current_user": user,
        "csrf_token": ensure_csrf_token(request),
        "content_type": content_type,
        "items": items,
        "title": "Posts" if content_type == ContentType.POST.value else "Pages",
    }


def form_context(
    request: Request,
    user: User,
    content_type: str,
    item: ContentItem | None = None,
    categories: list[Category] | None = None,
    tags: list[Tag] | None = None,
    selected_category_ids: set[int] | None = None,
    selected_tag_ids: set[int] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    publish_at_value = ""
    if item and item.publish_at:
        publish_at_value = item.publish_at.strftime("%Y-%m-%dT%H:%M")
    return {
        "current_user": user,
        "csrf_token": ensure_csrf_token(request),
        "content_type": content_type,
        "item": item,
        "categories": categories or [],
        "tags": tags or [],
        "selected_category_ids": selected_category_ids or set(),
        "selected_tag_ids": selected_tag_ids or set(),
        "publish_at_value": publish_at_value,
        "error": error,
        "title": "Post" if content_type == ContentType.POST.value else "Page",
    }


def get_content_or_404(session: Session, item_id: int, content_type: str) -> ContentItem:
    item = session.scalar(
        select(ContentItem)
        .where(ContentItem.id == item_id, ContentItem.content_type == content_type)
        .options(
            selectinload(ContentItem.categories),
            selectinload(ContentItem.tags),
            selectinload(ContentItem.author),
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found.")
    return item


def unique_slug(session: Session, title: str, exclude_id: int | None = None) -> str:
    base_slug = slugify(title)
    slug = base_slug
    counter = 2
    while True:
        query = select(ContentItem).where(ContentItem.slug == slug)
        if exclude_id is not None:
            query = query.where(ContentItem.id != exclude_id)
        if session.scalar(query) is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def assign_taxonomies(
    session: Session,
    item: ContentItem,
    category_ids: list[int],
    tag_ids: list[int],
) -> None:
    categories = []
    if category_ids:
        categories = list(session.scalars(select(Category).where(Category.id.in_(category_ids))).all())
    tags = []
    if tag_ids:
        tags = list(session.scalars(select(Tag).where(Tag.id.in_(tag_ids))).all())
    item.categories = categories
    item.tags = tags


def parse_id_list(values: list[str]) -> list[int]:
    result: list[int] = []
    for value in values:
        try:
            result.append(int(value))
        except ValueError:
            continue
    return result


def ensure_content_type(content_type: str) -> None:
    if content_type not in {ContentType.POST.value, ContentType.PAGE.value}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown content type.")


@router.get("/{content_type}")
def list_items(
    content_type: str,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    ensure_content_type(content_type)
    items = session.scalars(
        select(ContentItem)
        .where(ContentItem.content_type == content_type)
        .options(selectinload(ContentItem.author))
        .order_by(ContentItem.updated_at.desc())
    ).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "cms/list.html",
        list_context(request, user, content_type, items),
    )


@router.get("/{content_type}/new")
def new_item_form(
    content_type: str,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    ensure_content_type(content_type)
    categories = session.scalars(select(Category).order_by(Category.name)).all()
    tags = session.scalars(select(Tag).order_by(Tag.name)).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "cms/form.html",
        form_context(request, user, content_type, categories=categories, tags=tags),
    )


@router.post("/{content_type}")
def create_item(
    content_type: str,
    request: Request,
    title: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    body: Annotated[str, Form()] = "",
    excerpt: Annotated[str, Form()] = "",
    meta_title: Annotated[str, Form()] = "",
    meta_description: Annotated[str, Form()] = "",
    status_value: Annotated[str, Form()] = ContentStatus.DRAFT.value,
    publish_at: Annotated[str, Form()] = "",
    category_ids: Annotated[list[str], Form()] = [],
    tag_ids: Annotated[list[str], Form()] = [],
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    ensure_content_type(content_type)

    categories = session.scalars(select(Category).order_by(Category.name)).all()
    tags = session.scalars(select(Tag).order_by(Tag.name)).all()
    selected_category_ids = set(parse_id_list(category_ids))
    selected_tag_ids = set(parse_id_list(tag_ids))

    title = title.strip()
    if not title:
        return request.app.state.templates.TemplateResponse(
            request,
            "cms/form.html",
            form_context(
                request,
                user,
                content_type,
                categories=categories,
                tags=tags,
                selected_category_ids=selected_category_ids,
                selected_tag_ids=selected_tag_ids,
                error="Title is required.",
            ),
            status_code=400,
        )

    parsed_publish_at = parse_publish_at(publish_at)
    status_value, parsed_publish_at = normalize_status_and_publish_at(status_value, parsed_publish_at)
    if status_value == ContentStatus.SCHEDULED.value and parsed_publish_at is None:
        return request.app.state.templates.TemplateResponse(
            request,
            "cms/form.html",
            form_context(
                request,
                user,
                content_type,
                categories=categories,
                tags=tags,
                selected_category_ids=selected_category_ids,
                selected_tag_ids=selected_tag_ids,
                error="Scheduled content requires a publish date.",
            ),
            status_code=400,
        )

    hooks: HookRegistry = request.app.state.hooks
    item = ContentItem(
        title=title,
        slug=unique_slug(session, title),
        body=body.strip(),
        excerpt=excerpt.strip() or None,
        meta_title=meta_title.strip() or None,
        meta_description=meta_description.strip() or None,
        content_type=content_type,
        status=status_value,
        publish_at=parsed_publish_at,
        author_id=user.id,
    )
    assign_taxonomies(session, item, list(selected_category_ids), list(selected_tag_ids))
    hooks.do_action("content.before_save", item, user, is_new=True)
    session.add(item)
    session.commit()
    session.refresh(item)
    hooks.do_action("content.after_save", item, user, is_new=True)

    return RedirectResponse(url=f"/admin/content/{content_type}", status_code=303)


@router.get("/{content_type}/{item_id}/edit")
def edit_item_form(
    content_type: str,
    item_id: int,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    ensure_content_type(content_type)
    item = get_content_or_404(session, item_id, content_type)
    categories = session.scalars(select(Category).order_by(Category.name)).all()
    tags = session.scalars(select(Tag).order_by(Tag.name)).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "cms/form.html",
        form_context(
            request,
            user,
            content_type,
            item=item,
            categories=categories,
            tags=tags,
            selected_category_ids={c.id for c in item.categories},
            selected_tag_ids={t.id for t in item.tags},
        ),
    )


@router.post("/{content_type}/{item_id}")
def update_item(
    content_type: str,
    item_id: int,
    request: Request,
    title: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    body: Annotated[str, Form()] = "",
    excerpt: Annotated[str, Form()] = "",
    meta_title: Annotated[str, Form()] = "",
    meta_description: Annotated[str, Form()] = "",
    status_value: Annotated[str, Form()] = ContentStatus.DRAFT.value,
    publish_at: Annotated[str, Form()] = "",
    category_ids: Annotated[list[str], Form()] = [],
    tag_ids: Annotated[list[str], Form()] = [],
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    ensure_content_type(content_type)
    item = get_content_or_404(session, item_id, content_type)
    hooks: HookRegistry = request.app.state.hooks

    parsed_publish_at = parse_publish_at(publish_at)
    status_value, parsed_publish_at = normalize_status_and_publish_at(status_value, parsed_publish_at)

    item.title = title.strip()
    item.body = body.strip()
    item.excerpt = excerpt.strip() or None
    item.meta_title = meta_title.strip() or None
    item.meta_description = meta_description.strip() or None
    item.status = status_value
    item.publish_at = parsed_publish_at
    assign_taxonomies(session, item, parse_id_list(category_ids), parse_id_list(tag_ids))
    hooks.do_action("content.before_save", item, user, is_new=False)
    session.commit()
    session.refresh(item)
    hooks.do_action("content.after_save", item, user, is_new=False)
    return RedirectResponse(url=f"/admin/content/{content_type}", status_code=303)


@router.post("/{content_type}/{item_id}/delete")
def delete_item(
    content_type: str,
    item_id: int,
    request: Request,
    csrf_token: Annotated[str, Form()],
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value, UserRole.AUTHOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    ensure_content_type(content_type)
    item = get_content_or_404(session, item_id, content_type)
    session.delete(item)
    session.commit()
    return RedirectResponse(url=f"/admin/content/{content_type}", status_code=303)


@taxonomy_router.get("")
def taxonomy_admin(
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    categories = session.scalars(select(Category).order_by(Category.name)).all()
    tags = session.scalars(select(Tag).order_by(Tag.name)).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "cms/taxonomies.html",
        {
            "current_user": user,
            "csrf_token": ensure_csrf_token(request),
            "categories": categories,
            "tags": tags,
            "error": None,
        },
    )


@taxonomy_router.post("/categories")
def create_category(
    request: Request,
    name: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    name = name.strip()
    if not name:
        categories = session.scalars(select(Category).order_by(Category.name)).all()
        tags = session.scalars(select(Tag).order_by(Tag.name)).all()
        return request.app.state.templates.TemplateResponse(
            request,
            "cms/taxonomies.html",
            {
                "current_user": user,
                "csrf_token": ensure_csrf_token(request),
                "categories": categories,
                "tags": tags,
                "error": "Category name is required.",
            },
            status_code=400,
        )
    slug = slugify(name)
    existing = session.scalar(select(Category).where((Category.slug == slug) | (Category.name == name)))
    if existing:
        raise HTTPException(status_code=400, detail="Category already exists.")
    session.add(Category(name=name, slug=slug))
    session.commit()
    return RedirectResponse(url="/admin/taxonomies", status_code=303)


@taxonomy_router.post("/tags")
def create_tag(
    request: Request,
    name: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    name = name.strip()
    if not name:
        categories = session.scalars(select(Category).order_by(Category.name)).all()
        tags = session.scalars(select(Tag).order_by(Tag.name)).all()
        return request.app.state.templates.TemplateResponse(
            request,
            "cms/taxonomies.html",
            {
                "current_user": user,
                "csrf_token": ensure_csrf_token(request),
                "categories": categories,
                "tags": tags,
                "error": "Tag name is required.",
            },
            status_code=400,
        )
    slug = slugify(name)
    existing = session.scalar(select(Tag).where((Tag.slug == slug) | (Tag.name == name)))
    if existing:
        raise HTTPException(status_code=400, detail="Tag already exists.")
    session.add(Tag(name=name, slug=slug))
    session.commit()
    return RedirectResponse(url="/admin/taxonomies", status_code=303)


@taxonomy_router.post("/categories/{category_id}/delete")
def delete_category(
    category_id: int,
    request: Request,
    csrf_token: Annotated[str, Form()],
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    session.delete(category)
    session.commit()
    return RedirectResponse(url="/admin/taxonomies", status_code=303)


@taxonomy_router.post("/tags/{tag_id}/delete")
def delete_tag(
    tag_id: int,
    request: Request,
    csrf_token: Annotated[str, Form()],
    user: User = Depends(require_roles(UserRole.ADMIN.value, UserRole.EDITOR.value)),
    session: Session = Depends(get_db_session),
):
    validate_csrf(request, csrf_token)
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found.")
    session.delete(tag)
    session.commit()
    return RedirectResponse(url="/admin/taxonomies", status_code=303)
