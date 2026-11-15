import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Point the app at the test database *before* anything imports app.config / app.db.
_env = {**dotenv_values(BACKEND_DIR / ".env"), **os.environ}
TEST_DATABASE_URL = _env.get("TEST_DATABASE_URL")
if TEST_DATABASE_URL:
    if not make_url(TEST_DATABASE_URL).database.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must name a database ending in _test")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL


@pytest.fixture(scope="session")
def db_engine():
    """Drop, recreate and migrate the test database once per test run."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    from alembic import command
    from alembic.config import Config

    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")

    from app.db import engine

    yield engine
    engine.dispose()


@pytest.fixture
def session(db_engine):
    from app.db import SessionLocal

    with SessionLocal() as s:
        yield s


@pytest.fixture
def client(db_engine):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def seeded(session):
    """Fresh pilot data with no checks run yet. Returns {"CeraVe": sku_id, "Aveeno": sku_id}."""
    from app.seed import seed

    return seed(session, run_checks=False)["sku_ids"]


@pytest.fixture
def checked(seeded, client):
    """Pilot data with a check run on every SKU."""
    for sku_id in seeded.values():
        assert client.post(f"/skus/{sku_id}/run").status_code == 200
    return seeded
