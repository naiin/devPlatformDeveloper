import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from platform_app.api import app
from platform_app.db import engine
from platform_app.queue import redis_client


@pytest.fixture(scope="session", autouse=True)
def schema():
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def isolated_storage(schema):
    with engine().begin() as db:
        db.execute(text("TRUNCATE jobs"))
    redis_client().flushdb()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
