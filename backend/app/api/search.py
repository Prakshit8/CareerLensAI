"""Job search and personalized recommendation endpoints."""

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database.connection import get_db
from backend.app.database.models import CandidateProfile, JobFeedback, SearchHistory
from backend.app.database.schemas import SearchHit, SearchRequest, SearchResponse
from backend.app.ranking.scorer import score_job
from backend.app.search.service import SearchOutcome, search_jobs
from backend.app.search.vector import SemanticSearchUnavailable
from backend.app.services.profiles import (
    get_candidate_profile, get_candidate_context, record_search_history,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["search"])


def _feedback_map(db: Session, profile_id: int) -> dict[str, str]:
    rows = db.scalars(
        select(JobFeedback)
        .where(JobFeedback.profile_id == profile_id)
        .order_by(JobFeedback.created_at.desc())
    )
    latest: dict[str, str] = {}
    for row in rows:
        latest.setdefault(row.job_id, row.feedback)
    return latest


def _build_hits(
    db: Session,
    profile: CandidateProfile,
    outcome: SearchOutcome,
) -> list[SearchHit]:
    feedback = _feedback_map(db, profile.id)
    hits: list[SearchHit] = []
    for result in outcome.results:
        rank = score_job(
            result.job, profile, result.retrieval,
            feedback.get(result.job.id), settings.recommendation_weights,
        )
        explanations = rank.explanation
        if result.retrieval.get("semantic_score") is not None:
            explanations = [
                f"Semantic relevance: {result.retrieval['semantic_score']:.2f}",
                *explanations,
            ]
        hits.append(SearchHit(
            job=result.job,
            score=rank.score,
            explanation=explanations,
            retrieval={**result.retrieval, "components": rank.components,
                       "eligible": rank.eligible},
        ))
    return hits


def _run_search(
    db: Session,
    profile: CandidateProfile,
    query: str,
    mode: str,
    limit: int,
    filters: dict[str, str | None],
    *,
    record_history: bool = True,
) -> tuple[SearchResponse, float]:
    started = time.perf_counter()
    try:
        outcome = search_jobs(
            db, query, mode=mode, limit=limit,
            location=filters.get("location"),
            role=filters.get("role"),
            experience_level=filters.get("experience_level"),
            employment_type=filters.get("employment_type"),
        )
    except SemanticSearchUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    latency_ms = (time.perf_counter() - started) * 1000
    hits = _build_hits(db, profile, outcome)
    if record_history:
        record_search_history(
            db, profile.id, query=query, mode=mode, filters=filters,
            result_count=len(hits), latency_ms=latency_ms,
        )
        db.commit()
    return SearchResponse(
        query=query,
        mode=mode,
        results=hits,
        filters_applied={key: value for key, value in filters.items() if value},
        warnings=outcome.warnings,
    ), latency_ms


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    profile = get_candidate_profile(db)
    filters = {
        "location": payload.location,
        "role": payload.role,
        "experience_level": payload.experience_level,
        "employment_type": payload.employment_type,
    }
    return _run_search(db, profile, payload.query, payload.mode, payload.limit, filters)[0]


@router.get("/search/history")
def search_history(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    profile = get_candidate_profile(db)
    rows = db.scalars(
        select(SearchHistory)
        .where(SearchHistory.profile_id == profile.id)
        .order_by(SearchHistory.created_at.desc())
        .limit(limit)
    )
    return [
        {"id": row.id, "query": row.query, "mode": row.mode, "filters": row.filters,
         "result_count": row.result_count, "latency_ms": row.latency_ms,
         "created_at": row.created_at.isoformat()}
        for row in rows
    ]


@router.get("/recommendations", response_model=SearchResponse)
def recommendations(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SearchResponse:
    profile = get_candidate_profile(db)
    context = get_candidate_context(db, profile.id)
    memories = context.get("memories", {})
    locations = profile.preferred_locations or []
    if isinstance(memories, dict) and memories.get("preferred_locations"):
        remembered = memories["preferred_locations"]
        locations = remembered if isinstance(remembered, list) else [str(remembered)]
    query_parts = [
        *(profile.skills or []),
        *(profile.preferred_roles or []),
        profile.career_interests or "",
    ]
    query = " ".join(part for part in query_parts if part).strip()
    if not query:
        return SearchResponse(
            query="", mode="hybrid", results=[], filters_applied={},
            warnings=["Add skills, preferred roles, or career interests to get recommendations."],
        )
    response, _ = _run_search(
        db, profile, query, "hybrid", limit,
        {"location": None, "role": None, "experience_level": None,
         "employment_type": None},
        record_history=False,
    )
    feedback = _feedback_map(db, profile.id)
    response.results = [
        hit for hit in response.results
        if feedback.get(hit.job.id) not in {"dislike", "not_relevant"}
    ]
    if locations:
        for hit in response.results:
            if any(loc.casefold() in (hit.job.location or "").casefold() for loc in locations):
                hit.score = min(1.0, hit.score + 0.02)
    response.results.sort(key=lambda hit: (-hit.score, hit.job.id))
    return response
