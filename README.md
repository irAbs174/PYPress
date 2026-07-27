# PYpress

PYpress is a Python-based CMS inspired by WordPress and built on FastAPI.

## Features

- Session-based admin authentication with role checks
- Protected admin dashboard
- Posts and pages with draft/published states, excerpts, and SEO fields
- Categories and tags
- Media library (local uploads)
- Public site rendering via filesystem themes
- Plugin system with action/filter hooks
- SQLAlchemy models and Alembic migrations
- Server-rendered UI using Jinja2 templates

## Requirements

- Python 3.12+

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

The public site starts on `http://127.0.0.1:8000`.
Admin is at `http://127.0.0.1:8000/admin`.

Default bootstrap admin credentials:

- Email: `admin@example.com`
- Password: `admin12345`

Change them in `.env` before running outside local development.

If you already have an older local `pypress.db`, delete it (or run Alembic migrations) so the new schema is created.

## Environment

Create a `.env` file from `.env.example` and update any values as needed.

## Themes and plugins

- Themes live in `themes/<name>/` with `theme.json` and `templates/`
- Plugins live in `plugins/<name>/` with `plugin.json` and `plugin.py` exposing `register(app, hooks)`
- Uploads are stored in `uploads/` and served at `/uploads/...`
- Manage themes/plugins from the admin UI

Core hooks:

- `app.startup`
- `content.before_save` / `content.after_save`
- `public.before_render` (filter)

## Docker

Run PYpress with Docker Compose (app + PostgreSQL):

```bash
cp .env.example .env
docker compose up --build
```

The application starts on `http://127.0.0.1:8000`.

Useful commands:

```bash
docker compose up --build -d
docker compose logs -f web
docker compose down
```

Docker Compose overrides `DATABASE_URL` to use PostgreSQL. Change `SECRET_KEY` and `ADMIN_PASSWORD` in `.env` before deploying.

## Tests

```bash
pytest
```

## Project Layout

```text
app/
  admin/
  auth/
  cms/
  core/
  database/
  media/
  plugins/
  themes/
  static/
  templates/
themes/
plugins/
uploads/
migrations/
scripts/
tests/
```
