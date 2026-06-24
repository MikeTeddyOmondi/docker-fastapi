"""Shared pytest fixtures.

The database URL is pointed at a throwaway temp SQLite file *before* the app is
imported, because ``app.db`` builds its engine from settings at import time. The
RabbitMQ consumer is stubbed out so the suite never needs a live broker.
"""

import os
import tempfile

# Must run before any `app.*` import so config/engine pick it up.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="docker-api-test-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_broker(monkeypatch):
    """Stop the lifespan from dialing RabbitMQ during tests."""

    async def _noop_start():
        return None

    async def _noop_shutdown(_connection):
        return None

    monkeypatch.setattr("app.main.start_consumer", _noop_start)
    monkeypatch.setattr("app.main.shutdown_consumer", _noop_shutdown)


@pytest.fixture
def client():
    """A TestClient with a freshly reset schema for each test."""
    from app import db
    from app.main import app

    SQLModel.metadata.drop_all(db.engine)
    SQLModel.metadata.create_all(db.engine)

    with TestClient(app) as test_client:
        yield test_client
