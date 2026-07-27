#!/bin/sh
set -e

if echo "$DATABASE_URL" | grep -q '^postgresql'; then
  python scripts/wait_for_db.py
  alembic upgrade head
fi

exec "$@"
