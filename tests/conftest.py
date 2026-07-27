import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_DB_PATH = Path("test_pypress.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.name}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "admin12345"

from app.database.base import Base
from app.database.init_db import seed_admin
from app.database.session import SessionLocal, engine
from app.main import create_app


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_admin(session)
    yield


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def cleanup_database():
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
