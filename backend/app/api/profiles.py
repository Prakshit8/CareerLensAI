"""Candidate profile endpoints."""

import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.app.database.connection import get_db
from backend.app.database.models import CandidateProfile
from backend.app.database.schemas import ProfileOut, ProfileUpdate
from backend.app.services.profiles import get_candidate_profile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/profiles", tags=["profiles"])

SKILL_VOCABULARY = {
    "python", "java", "javascript", "typescript", "sql", "pytorch", "tensorflow",
    "scikit-learn", "machine learning", "deep learning", "nlp", "rag", "llm",
    "generative ai", "fastapi", "django", "streamlit", "docker", "kubernetes",
    "aws", "azure", "gcp", "faiss", "langchain", "data analysis", "pandas",
}


def _profile_out(profile: CandidateProfile) -> ProfileOut:
    fields = (
        "id", "identity", "name", "email", "skills", "experience_level", "education",
        "preferred_roles", "preferred_locations", "preferred_employment_types",
        "salary_min", "salary_max", "career_interests", "resume_text",
        "created_at", "updated_at",
    )
    data = {field: getattr(profile, field) for field in fields}
    completed = sum(
        bool(data.get(field))
        for field in ("name", "skills", "experience_level", "preferred_roles", "preferred_locations")
    )
    data["completion_status"] = f"{round(completed / 5 * 100)}%"
    return ProfileOut.model_validate(data)


@router.get("/me", response_model=ProfileOut)
def read_profile(db: Session = Depends(get_db)) -> ProfileOut:
    return _profile_out(get_candidate_profile(db))


@router.patch("/me", response_model=ProfileOut)
def update_profile(payload: ProfileUpdate, db: Session = Depends(get_db)) -> ProfileOut:
    profile = get_candidate_profile(db)
    values = payload.model_dump(exclude_unset=True)
    min_salary = values.get("salary_min", profile.salary_min)
    max_salary = values.get("salary_max", profile.salary_max)
    if min_salary is not None and max_salary is not None and min_salary > max_salary:
        raise HTTPException(status_code=422, detail="salary_min cannot exceed salary_max.")
    for field, value in values.items():
        if field in {"skills", "preferred_roles", "preferred_locations",
                     "preferred_employment_types"} and value is not None:
            value = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)


@router.post("/me/resume", response_model=ProfileOut)
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ProfileOut:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Upload a PDF resume.")
    content = await file.read(5_000_001)
    if len(content) > 5_000_000:
        raise HTTPException(status_code=413, detail="Resume must be 5 MB or smaller.")
    try:
        from pypdf import PdfReader

        pages = PdfReader(io.BytesIO(content)).pages
        resume_text = "\n".join(page.extract_text() or "" for page in pages).strip()
    except Exception as error:
        logger.exception("Could not extract text from uploaded PDF")
        raise HTTPException(status_code=422, detail="Could not read the PDF resume.") from error
    if not resume_text:
        raise HTTPException(status_code=422, detail="No selectable text was found in the PDF.")

    profile = get_candidate_profile(db)
    extracted = sorted(
        (skill for skill in SKILL_VOCABULARY if skill.casefold() in resume_text.casefold())
    )
    profile.resume_text = resume_text
    if extracted:
        existing = {skill.casefold() for skill in profile.skills}
        profile.skills = profile.skills + [skill for skill in extracted if skill.casefold() not in existing]
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)
