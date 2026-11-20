"""Build or refresh the persisted CPU FAISS job index."""

from sqlalchemy import select

from backend.app.database import models  # noqa: F401
from backend.app.database.connection import Base, SessionLocal, engine
from backend.app.database.models import Job
from backend.app.search.vector import semantic_index


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        jobs = list(db.scalars(select(Job).order_by(Job.id)))
    if not jobs:
        raise SystemExit("No jobs are indexed. Import a dataset first.")
    count = semantic_index.build(jobs)
    print(f"Indexed {count} jobs with the configured CPU embedding model.")


if __name__ == "__main__":
    main()
