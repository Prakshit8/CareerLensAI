"""Filtered keyword, semantic, and reciprocal-rank-fusion job retrieval."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database.models import Job
from backend.app.search.bm25 import BM25Index
from backend.app.search.vector import SemanticSearchUnavailable, searchable_text, semantic_index

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    job: Job
    score: float
    retrieval: dict[str, float | int | None] = field(default_factory=dict)


@dataclass
class SearchOutcome:
    results: list[SearchResult]
    warnings: list[str] = field(default_factory=list)


def _filtered_jobs(
    db: Session,
    *,
    location: str | None = None,
    role: str | None = None,
    experience_level: str | None = None,
    employment_type: str | None = None,
) -> list[Job]:
    now = datetime.now(timezone.utc)
    jobs = list(
        db.scalars(
            select(Job).where(or_(Job.expires_at.is_(None), Job.expires_at >= now))
            .order_by(Job.created_at.desc())
        )
    )
    filters = (
        (location, lambda job: job.location),
        (role, lambda job: " ".join((job.title, job.role_category or ""))),
        (experience_level, lambda job: job.experience_level),
        (employment_type, lambda job: job.employment_type),
    )
    for wanted, getter in filters:
        if wanted:
            folded = wanted.casefold()
            jobs = [
                job for job in jobs
                if getter(job) and folded in getter(job).casefold()
            ]
    return jobs


def search_jobs(
    db: Session,
    query: str,
    *,
    mode: str = "hybrid",
    limit: int = 20,
    location: str | None = None,
    role: str | None = None,
    experience_level: str | None = None,
    employment_type: str | None = None,
    rrf_constant: int | None = None,
) -> SearchOutcome:
    if not query.strip():
        raise ValueError("Search query cannot be blank.")
    if mode not in {"keyword", "semantic", "hybrid"}:
        raise ValueError("Search mode must be keyword, semantic, or hybrid.")
    if rrf_constant is None:
        rrf_constant = settings.rrf_constant
    if rrf_constant <= 0:
        raise ValueError("RRF constant must be positive.")
    jobs = _filtered_jobs(
        db, location=location, role=role,
        experience_level=experience_level, employment_type=employment_type,
    )
    if not jobs:
        return SearchOutcome([])
    texts = [searchable_text(job) for job in jobs]
    bm25_scores = BM25Index(texts).scores(query)
    keyword_ranked = [
        (jobs[index].id, score)
        for index, score in sorted(
            enumerate(bm25_scores), key=lambda item: (-item[1], jobs[item[0]].id)
        )
        if score > 0
    ]
    semantic_scores: dict[str, float] = {}
    warnings: list[str] = []
    if mode in {"semantic", "hybrid"}:
        try:
            semantic_scores = semantic_index.search(query, jobs, max(limit * 5, 50))
        except SemanticSearchUnavailable as error:
            if mode == "semantic":
                raise
            warnings.append(f"Semantic retrieval is unavailable; hybrid results use BM25 only: {error}")
            logger.warning("%s", warnings[-1])

    if mode == "keyword":
        ranked_ids = [job_id for job_id, _ in keyword_ranked[:limit]]
        result_scores = {job_id: score for job_id, score in keyword_ranked}
        keyword_ranks = {job_id: rank for rank, (job_id, _) in enumerate(keyword_ranked, 1)}
    elif mode == "semantic":
        ranked_ids = list(semantic_scores.keys())[:limit]
        result_scores = semantic_scores
        keyword_ranks = {}
    else:
        keyword_ranks = {job_id: rank for rank, (job_id, _) in enumerate(keyword_ranked, 1)}
        semantic_ranks = {
            job_id: rank for rank, job_id in enumerate(semantic_scores.keys(), 1)
        }
        all_ids = set(keyword_ranks) | set(semantic_ranks)
        result_scores = {
            job_id: (
                (1 / (rrf_constant + keyword_ranks[job_id]) if job_id in keyword_ranks else 0)
                + (1 / (rrf_constant + semantic_ranks[job_id]) if job_id in semantic_ranks else 0)
            )
            for job_id in all_ids
        }
        ranked_ids = sorted(all_ids, key=lambda job_id: (-result_scores[job_id], job_id))[:limit]

    jobs_by_id = {job.id: job for job in jobs}
    result_by_id = {job_id: score for job_id, score in keyword_ranked}
    return SearchOutcome(
        results=[
            SearchResult(
                job=jobs_by_id[job_id],
                score=float(result_scores[job_id]),
                retrieval={
                    "keyword_score": result_by_id.get(job_id),
                    "keyword_rank": keyword_ranks.get(job_id),
                    "semantic_score": semantic_scores.get(job_id),
                },
            )
            for job_id in ranked_ids if job_id in jobs_by_id
        ],
        warnings=warnings,
    )
