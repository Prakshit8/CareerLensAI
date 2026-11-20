"""Create database tables and optionally ingest a CSV dataset."""

import argparse
import json
from pathlib import Path

from backend.app.database.connection import Base, SessionLocal, engine
from backend.app.database import models  # noqa: F401
from backend.app.ingestion.csv_source import CSVJobSource
from backend.app.ingestion.json_source import JSONJobSource
from backend.app.services.ingestion import import_source
from backend.app.config import PROJECT_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", "--input", dest="csv", type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "jobs.csv",
    )
    parser.add_argument("--source", default="synthetic-demo")
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    if args.csv.suffix.casefold() == ".json":
        source = JSONJobSource(args.csv, args.source)
    else:
        source = CSVJobSource(args.csv, args.source)
    with SessionLocal() as db:
        report = import_source(db, source)
    print(json.dumps(report.__dict__, indent=2))


if __name__ == "__main__":
    main()
