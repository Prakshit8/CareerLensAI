"""Saved jobs and feedback endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database.connection import get_db
from backend.app.database.models import Job, JobFeedback, SavedJob
from backend.app.database.schemas import FeedbackWrite, JobOut
from backend.app.services.profiles import get_candidate_profile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["engagement"])


@router.get("/saved", response_model=list[JobOut])
def list_saved(db: Session = Depends(get_db)) -> list[Job]:
    profile = get_candidate_profile(db)
    return list(
        db.scalars(
            select(Job).join(SavedJob, SavedJob.job_id == Job.id)
            .where(SavedJob.profile_id == profile.id)
            .order_by(SavedJob.created_at.desc())
        )
    )


@router.put("/saved/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def save_job(job_id: str, db: Session = Depends(get_db)) -> None:
    profile = get_candidate_profile(db)
    if db.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    exists = db.scalar(
        select(SavedJob.id).where(
            SavedJob.profile_id == profile.id, SavedJob.job_id == job_id
        )
    )
    if exists is None:
        db.add(SavedJob(profile_id=profile.id, job_id=job_id))
        db.commit()


@router.delete("/saved/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsave_job(job_id: str, db: Session = Depends(get_db)) -> None:
    profile = get_candidate_profile(db)
    saved = db.scalar(
        select(SavedJob).where(
            SavedJob.profile_id == profile.id, SavedJob.job_id == job_id
        )
    )
    if saved is not None:
        db.delete(saved)
        db.commit()


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def record_feedback(payload: FeedbackWrite, db: Session = Depends(get_db)) -> dict[str, str]:
    profile = get_candidate_profile(db)
    if db.get(Job, payload.job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    db.add(JobFeedback(
        profile_id=profile.id, job_id=payload.job_id, feedback=payload.feedback
    ))
    db.commit()
    return {"status": "recorded", "feedback": payload.feedback}
