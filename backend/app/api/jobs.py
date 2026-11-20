"""Job listing and CRUD endpoints."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.database.connection import get_db
from backend.app.database.models import Job
from backend.app.database.schemas import JobCreate, JobOut, SearchResponse
from backend.app.api.search import _run_search
from backend.app.services.ingestion import stable_job_id
from backend.app.services.profiles import get_candidate_profile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(
    q: str | None = None,
    location: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Job]:
    query = select(Job).where(
        or_(Job.expires_at.is_(None), Job.expires_at >= datetime.now(timezone.utc))
    )
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(
            or_(Job.title.ilike(term), Job.company.ilike(term), Job.description.ilike(term))
        )
    if location:
        query = query.where(Job.location.ilike(f"%{location.strip()}%"))
    return list(
        db.scalars(query.order_by(Job.posted_at.desc().nullslast(), Job.created_at.desc())
                   .offset(offset).limit(limit))
    )


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: Session = Depends(get_db)) -> Job:
    external_id = payload.external_id or stable_job_id(
        payload.source, f"{payload.title}|{payload.company}|{payload.apply_url or ''}"
    )
    job = db.scalar(
        select(Job).where(Job.source == payload.source, Job.external_id == external_id)
    )
    values = payload.model_dump()
    values["external_id"] = external_id
    values["id"] = stable_job_id(payload.source, external_id)
    if job is None:
        job = Job(**values)
        db.add(job)
    else:
        for field, value in values.items():
            if field != "id":
                setattr(job, field, value)
    try:
        db.commit()
        db.refresh(job)
    except Exception as error:
        db.rollback()
        logger.exception("Could not save job")
        raise HTTPException(status_code=500, detail="Could not save job.") from error
    return job


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.get("/{job_id}/similar", response_model=SearchResponse)
def similar_jobs(
    job_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> SearchResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    from backend.app.search.vector import SemanticSearchUnavailable

    try:
        response, _ = _run_search(
            db, get_candidate_profile(db),
            " ".join((job.title, job.role_category or "", " ".join(job.skills or []))),
            "hybrid", limit + 1, {},
        )
    except SemanticSearchUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    response.results = [hit for hit in response.results if hit.job.id != job_id][:limit]
    return response
