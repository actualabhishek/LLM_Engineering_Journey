import os
from pathlib import Path

# Must run before any `app.*` import: app.config.Settings() reads DATABASE_URL
# from the environment at import time, and app.db builds the engine from it.
_TEST_DB_PATH = Path(__file__).parent / "_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

import pytest  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_db(db_session):
    seed()
    yield db_session


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()
