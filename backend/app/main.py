"""FastAPI application entry point and database lifecycle."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from backend.app.api import assistant, engagement, evaluation, jobs, memory, profiles, search
from backend.app.database.connection import Base, SessionLocal, engine
from backend.app.database import models  # noqa: F401
from backend.app.services.profiles import get_candidate_profile


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create the local schema and demo identity before accepting requests."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        get_candidate_profile(db)
    yield


app = FastAPI(title="CareerLens AI", version="1.0.0", lifespan=lifespan)
app.include_router(jobs.router)
app.include_router(profiles.router)
app.include_router(memory.router)
app.include_router(search.router)
app.include_router(engagement.router)
app.include_router(assistant.router)
app.include_router(evaluation.router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "CareerLens AI", "docs": "/docs"}
