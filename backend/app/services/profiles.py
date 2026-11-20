"""Candidate profile and explicit preference memory helpers."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database.models import CandidateMemory, CandidateProfile, SearchHistory


def get_candidate_profile(db: Session) -> CandidateProfile:
    """Get the configured local profile or create its empty first-run record."""
    profile = db.scalar(
        select(CandidateProfile).where(CandidateProfile.identity == settings.demo_identity)
    )
    if profile is None:
        profile = CandidateProfile(identity=settings.demo_identity)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def update_memory(
    db: Session,
    profile_id: int,
    *,
    kind: str,
    key: str,
    value: object,
    is_explicit: bool,
) -> CandidateMemory | None:
    """Upsert memory without allowing inferred data to replace explicit input."""
    normalized_key = key.strip().casefold()
    existing = db.scalar(
        select(CandidateMemory).where(
            CandidateMemory.profile_id == profile_id,
            CandidateMemory.key == normalized_key,
        )
    )
    if existing is not None and existing.is_explicit and not is_explicit:
        return existing
    if existing is None:
        existing = CandidateMemory(
            profile_id=profile_id,
            kind=kind.strip().casefold(),
            key=normalized_key,
            value=value,
            is_explicit=is_explicit,
        )
        db.add(existing)
    else:
        existing.kind = kind.strip().casefold()
        existing.value = value
        existing.is_explicit = is_explicit
    profile_field = {
        "preferred_locations": "preferred_locations",
        "preferred_roles": "preferred_roles",
        "preferred_employment_types": "preferred_employment_types",
    }.get(normalized_key)
    if profile_field:
        profile = db.get(CandidateProfile, profile_id)
        if profile is not None and (is_explicit or not getattr(profile, profile_field)):
            normalized_value = value if isinstance(value, list) else [value]
            setattr(profile, profile_field, [str(item) for item in normalized_value if item])
    return existing


def save_memory(
    db: Session,
    profile_id: int,
    *,
    kind: str,
    key: str,
    value: object,
    is_explicit: bool = True,
) -> CandidateMemory | None:
    """Create or update a persistent memory using the explicitness guard."""
    return update_memory(
        db, profile_id, kind=kind, key=key, value=value,
        is_explicit=is_explicit,
    )


def retrieve_memories(
    db: Session,
    profile_id: int,
    *,
    query: str | None = None,
    kind: str | None = None,
) -> list[CandidateMemory]:
    """Retrieve all memories or only those relevant to a query and memory kind."""
    statement = select(CandidateMemory).where(CandidateMemory.profile_id == profile_id)
    if kind:
        statement = statement.where(CandidateMemory.kind == kind.casefold())
    memories = list(db.scalars(statement.order_by(CandidateMemory.updated_at.desc())))
    if not query or not query.strip():
        return memories
    terms = set(query.casefold().split())
    return [
        memory for memory in memories
        if any(term in memory.key or term in str(memory.value).casefold() for term in terms)
    ]


def delete_memory(db: Session, profile_id: int, memory_id: int) -> bool:
    """Delete one memory owned by the profile and clear its profile preference."""
    memory = db.get(CandidateMemory, memory_id)
    if memory is None or memory.profile_id != profile_id:
        return False
    profile_field = {
        "preferred_locations": "preferred_locations",
        "preferred_roles": "preferred_roles",
        "preferred_employment_types": "preferred_employment_types",
    }.get(memory.key)
    if profile_field:
        setattr(db.get(CandidateProfile, profile_id), profile_field, [])
    db.delete(memory)
    return True


def record_search_history(
    db: Session,
    profile_id: int,
    *,
    query: str,
    mode: str,
    filters: dict[str, object],
    result_count: int,
    latency_ms: float,
) -> SearchHistory:
    """Add an immutable search event to persistent history."""
    record = SearchHistory(
        profile_id=profile_id,
        query=query,
        mode=mode,
        filters=filters,
        result_count=result_count,
        latency_ms=latency_ms,
    )
    db.add(record)
    return record


def get_candidate_context(db: Session, profile_id: int) -> dict[str, object]:
    """Return only the profile and preferences needed for job matching."""
    profile = db.get(CandidateProfile, profile_id)
    if profile is None:
        return {}
    memories = retrieve_memories(db, profile_id)
    return {
        "skills": profile.skills,
        "experience_level": profile.experience_level,
        "preferred_roles": profile.preferred_roles,
        "preferred_locations": profile.preferred_locations,
        "preferred_employment_types": profile.preferred_employment_types,
        "career_interests": profile.career_interests,
        "memories": {memory.key: memory.value for memory in memories},
    }
