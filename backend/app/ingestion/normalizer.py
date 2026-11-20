"""Validation and normalization for heterogeneous job source records."""

import hashlib
import re
from typing import Any

from pydantic import ValidationError

from backend.app.database.schemas import JobCreate


FIELD_ALIASES = {
    "apply_url": ("apply_url", "url", "apply_link", "link"),
    "employment_type": ("employment_type", "job_type", "type"),
    "experience_level": ("experience_level", "seniority", "level"),
    "salary_min": ("salary_min", "min_salary"),
    "salary_max": ("salary_max", "max_salary"),
    "skills": ("skills", "required_skills"),
    "role_category": ("role_category", "category"),
    "posted_at": ("posted_at", "date_posted"),
}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _as_salary(value: Any) -> float | None:
    text = _clean_text(value)
    if text is None:
        return None
    cleaned = re.sub(r"[^0-9.]", "", text)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def normalize_job(record: dict[str, Any], source: str) -> JobCreate:
    """Map aliases, clean text, and validate a source record."""
    data: dict[str, Any] = dict(record)
    for target, aliases in FIELD_ALIASES.items():
        if target not in data:
            data[target] = next((record[key] for key in aliases if key in record), None)

    for field in ("title", "company", "description", "location", "employment_type",
                  "experience_level", "role_category", "apply_url"):
        if field in data:
            data[field] = _clean_text(data[field])

    skills = data.get("skills")
    if isinstance(skills, str):
        data["skills"] = [part.strip() for part in re.split(r"[,;|]", skills) if part.strip()]
    elif skills is None:
        data["skills"] = []

    for salary_field in ("salary_min", "salary_max"):
        data[salary_field] = _as_salary(data.get(salary_field))

    data["source"] = source
    data["title"] = data.get("title") or ""
    data["company"] = data.get("company") or "Undisclosed"
    data["description"] = data.get("description") or ""
    external_id = _clean_text(data.get("external_id"))
    if not external_id:
        identity = "|".join(
            (str(data["title"]).casefold(), str(data["company"]).casefold(),
             str(data.get("apply_url") or "").casefold())
        )
        external_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    data["external_id"] = external_id
    return JobCreate.model_validate(data)
