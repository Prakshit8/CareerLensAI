"""Isolated API and database fixtures."""

import os

os.environ["DATABASE_URL"] = "sqlite:///./data/test-isolated.sqlite3"
os.environ["GROQ_API_KEY"] = ""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api import assistant, engagement, evaluation, jobs, memory, profiles, search
from backend.app.database.connection import Base, get_db

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=TEST_ENGINE, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=TEST_ENGINE)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture
def client(db_session):
    app = FastAPI()
    for router in (
        jobs.router, profiles.router, memory.router, search.router,
        engagement.router, assistant.router, evaluation.router,
    ):
        app.include_router(router)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
