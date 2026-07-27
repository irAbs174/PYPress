from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.cms.models import Category, ContentItem, ContentStatus, ContentType, Tag
from app.cms.settings import get_setting
from app.core.config import get_settings
from app.database.session import get_db_session
from app.plugins.hooks import HookRegistry


router = APIRouter(tags=["public"])


def published_posts_query():
    return (
        select(ContentItem)
        .where(
            ContentItem.content_type == ContentType.POST.value,
            ContentItem.status == ContentStatus.PUBLISHED.value,
        )
        .options(selectinload(ContentItem.categories), selectinload(ContentItem.tags), selectinload(ContentItem.author))
        .order_by(ContentItem.updated_at.desc())
    )


def site_context(request: Request, session: Session, **extra):
    settings = get_settings()
    hooks: HookRegistry = request.app.state.hooks
    context = {
        "site_title": get_setting(session, "site_title", settings.app_name),
        "site_tagline": get_setting(session, "site_tagline", "A Python CMS"),
        "request": request,
        "current_user": None,
        **extra,
    }
    return hooks.apply_filters("public.before_render", context, request)


@router.get("/")
def home(request: Request, session: Session = Depends(get_db_session)):
    posts = session.scalars(published_posts_query()).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "home.html",
        site_context(request, session, posts=posts, page_title=None),
    )


@router.get("/posts/{slug}")
def single_post(slug: str, request: Request, session: Session = Depends(get_db_session)):
    item = session.scalar(
        select(ContentItem)
        .where(
            ContentItem.slug == slug,
            ContentItem.content_type == ContentType.POST.value,
            ContentItem.status == ContentStatus.PUBLISHED.value,
        )
        .options(selectinload(ContentItem.categories), selectinload(ContentItem.tags), selectinload(ContentItem.author))
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")
    return request.app.state.templates.TemplateResponse(
        request,
        "single_post.html",
        site_context(request, session, item=item, page_title=item.meta_title or item.title),
    )


@router.get("/pages/{slug}")
def single_page(slug: str, request: Request, session: Session = Depends(get_db_session)):
    item = session.scalar(
        select(ContentItem)
        .where(
            ContentItem.slug == slug,
            ContentItem.content_type == ContentType.PAGE.value,
            ContentItem.status == ContentStatus.PUBLISHED.value,
        )
        .options(selectinload(ContentItem.categories), selectinload(ContentItem.tags), selectinload(ContentItem.author))
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found.")
    return request.app.state.templates.TemplateResponse(
        request,
        "single_page.html",
        site_context(request, session, item=item, page_title=item.meta_title or item.title),
    )


@router.get("/category/{slug}")
def category_archive(slug: str, request: Request, session: Session = Depends(get_db_session)):
    category = session.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    posts = session.scalars(
        published_posts_query().where(ContentItem.categories.any(Category.id == category.id))
    ).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "archive.html",
        site_context(
            request,
            session,
            posts=posts,
            archive_title=f"Category: {category.name}",
            page_title=f"Category: {category.name}",
        ),
    )


@router.get("/tag/{slug}")
def tag_archive(slug: str, request: Request, session: Session = Depends(get_db_session)):
    tag = session.scalar(select(Tag).where(Tag.slug == slug))
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found.")
    posts = session.scalars(
        published_posts_query().where(ContentItem.tags.any(Tag.id == tag.id))
    ).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "archive.html",
        site_context(
            request,
            session,
            posts=posts,
            archive_title=f"Tag: {tag.name}",
            page_title=f"Tag: {tag.name}",
        ),
    )


@router.get("/robots.txt", response_class=Response)
def robots_txt(request: Request):
    body = f"User-agent: *\nAllow: /\nSitemap: {request.base_url}sitemap.xml\n"
    return Response(content=body, media_type="text/plain")


@router.get("/sitemap.xml", response_class=Response)
def sitemap_xml(request: Request, session: Session = Depends(get_db_session)):
    items = session.scalars(
        select(ContentItem)
        .where(ContentItem.status == ContentStatus.PUBLISHED.value)
        .order_by(ContentItem.updated_at.desc())
    ).all()
    urls = [f"  <url><loc>{request.base_url}</loc></url>"]
    for item in items:
        if item.content_type == ContentType.POST.value:
            loc = f"{request.base_url}posts/{item.slug}"
        else:
            loc = f"{request.base_url}pages/{item.slug}"
        lastmod = item.updated_at.date().isoformat() if item.updated_at else ""
        urls.append(f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod></url>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")
