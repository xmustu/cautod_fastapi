import os
import sys
import datetime
import asyncio
import pytest

# Ensure project package root is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient

import database.redis as db_redis
from core.authentication import get_current_active_user, User


class DummyRedis:
    async def ping(self):
        return True

    async def aclose(self):
        return True

    async def hdel(self, *args, **kwargs):
        return 0

    async def delete(self, *args, **kwargs):
        return 0


async def _fake_redis_connect():
    return DummyRedis()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def app_client():
    """Provide a TestClient for the FastAPI app with safe test overrides."""
    # monkeypatch the redis connector used in the app lifespan so startup won't try to connect to a real Redis
    db_redis.redis_connect = _fake_redis_connect

    # import app after we've patched redis_connect
    from main import app

    # override authentication dependency to return a simple test user
    async def _fake_user():
        return User(user_id=1, email="test@example.com", created_at=datetime.datetime.utcnow())

    app.dependency_overrides[get_current_active_user] = _fake_user

    client = TestClient(app)
    yield client
    client.close()


@pytest.fixture(autouse=True)
def clean_files(tmp_path):
    """Provide a temporary workspace for file writes under ./files during tests.
    Tests should create files under the created directory and this fixture ensures they are isolated.
    """
    # change working dir to temp to avoid polluting repo files
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield
    finally:
        os.chdir(old_cwd)
