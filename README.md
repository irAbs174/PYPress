# PYpress

PYpress is a Python-based CMS MVP inspired by WordPress and built on FastAPI.

## Features

- Session-based admin authentication with role checks
- Protected admin dashboard
- Post and page management with draft/published states
- SQLAlchemy models and Alembic migration scaffold
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

The application starts on `http://127.0.0.1:8000`.

Default bootstrap admin credentials:

- Email: `admin@example.com`
- Password: `admin12345`

Change them in `.env` before running outside local development.

## Environment

Create a `.env` file from `.env.example` and update any values as needed.

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
  static/
  templates/
migrations/
scripts/
tests/
```
