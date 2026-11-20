"""Idempotent database ingestion for normalized job records."""

import hashlib
import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database.models import Job
from backend.app.ingestion.base import ImportReport, JobSource
from backend.app.ingestion.normalizer import normalize_job

logger = logging.getLogger(__name__)


def stable_job_id(source: str, external_id: str) -> str:
    """Return a deterministic primary key for a source record."""
    return hashlib.sha256(f"{source}:{external_id}".encode("utf-8")).hexdigest()


def import_source(db: Session, source: JobSource) -> ImportReport:
    """Normalize and upsert source records while isolating invalid rows."""
    records = source.iter_records()
    report = ImportReport(source=source.source_name, total=len(records))
    staged: dict[str, Job] = {}
    for row_number, record in enumerate(records, start=2):
        try:
            data = normalize_job(record, source.source_name)
        except (ValidationError, TypeError, ValueError) as error:
            report.skipped += 1
            if isinstance(error, ValidationError):
                detail = "; ".join(
                    f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                    for item in error.errors()
                )
            else:
                detail = str(error)
            report.errors.append(f"row {row_number}: {detail}")
            logger.warning("Skipping invalid job row %s: %s", row_number, detail)
            continue

        key = f"{source.source_name}:{data.external_id}"
        job = staged.get(key) or db.scalar(
            select(Job).where(Job.source == source.source_name,
                              Job.external_id == data.external_id)
        )
        values = data.model_dump()
        values["id"] = stable_job_id(source.source_name, data.external_id or "")
        if job is None:
            job = Job(**values)
            db.add(job)
            report.inserted += 1
        else:
            for field_name, value in values.items():
                if field_name != "id":
                    setattr(job, field_name, value)
            report.updated += 1
        staged[key] = job
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not commit job import for source %s", source.source_name)
        raise
    return report
