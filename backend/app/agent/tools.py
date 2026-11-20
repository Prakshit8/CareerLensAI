"""Validated Python tools used by the optional LLM agent."""

import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database.models import (
    CandidateProfile, Job, JobFeedback, SavedJob,
)
from backend.app.database.schemas import FeedbackWrite, JobOut, MemoryWrite, ProfileUpdate
from backend.app.ranking.scorer import score_job
from backend.app.search.service import search_jobs
from backend.app.search.vector import SemanticSearchUnavailable, searchable_text
from backend.app.services.profiles import get_candidate_context, update_memory

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS = [
    ("search_jobs", "Search jobs with keyword, semantic, or hybrid retrieval.",
     {"query": {"type": "string"}, "mode": {"type": "string", "enum": ["keyword", "semantic", "hybrid"]},
      "limit": {"type": "integer"}}, ["query"]),
    ("semantic_search", "Find jobs using semantic similarity.",
     {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
    ("hybrid_search", "Combine semantic and BM25 keyword retrieval.",
     {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
    ("get_candidate_profile", "Read the local candidate profile.",
     {}, []),
    ("update_candidate_profile", "Update fields the candidate explicitly provided.",
     {"name": {"type": "string"}, "skills": {"type": "array", "items": {"type": "string"}},
      "experience_level": {"type": "string"}, "preferred_roles": {"type": "array", "items": {"type": "string"}},
      "preferred_locations": {"type": "array", "items": {"type": "string"}},
      "preferred_employment_types": {"type": "array", "items": {"type": "string"}},
      "career_interests": {"type": "string"}}, []),
    ("retrieve_memories", "Retrieve relevant saved preferences and memory.",
     {"query": {"type": "string"}}, ["query"]),
    ("update_memory", "Save an explicit user preference or memory.",
     {"kind": {"type": "string"}, "key": {"type": "string"},
      "value": {}, "is_explicit": {"type": "boolean"}}, ["kind", "key", "value"]),
    ("recommend_jobs", "Rank active jobs using the candidate profile.",
     {"limit": {"type": "integer"}}, []),
    ("get_similar_jobs", "Find jobs similar to a selected job.",
     {"job_id": {"type": "string"}, "limit": {"type": "integer"}}, ["job_id"]),
    ("save_job", "Save a job to the candidate's list.",
     {"job_id": {"type": "string"}}, ["job_id"]),
    ("record_feedback", "Record candidate feedback for a job.",
     {"job_id": {"type": "string"}, "feedback": {"type": "string",
      "enum": ["like", "dislike", "not_relevant", "applied"]}}, ["job_id", "feedback"]),
    ("get_saved_jobs", "List jobs the candidate has saved.", {}, []),
]

GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }
    for name, description, properties, required in TOOL_DEFINITIONS
]


def _job_result(result: Any, profile: CandidateProfile) -> dict[str, Any]:
    scored = score_job(
        result.job, profile, result.retrieval,
        weights=settings.recommendation_weights,
    )
    return {
        "job": JobOut.model_validate(result.job).model_dump(mode="json"),
        "score": scored.score,
        "explanation": scored.explanation,
        "retrieval": {**result.retrieval, "components": scored.components,
                      "eligible": scored.eligible},
    }


def _search(
    db: Session,
    profile: CandidateProfile,
    query: str,
    mode: str,
    limit: int,
) -> dict[str, Any]:
    request_mode = mode
    try:
        outcome = search_jobs(db, query, mode=request_mode, limit=max(1, min(limit, 20)))
    except SemanticSearchUnavailable:
        if request_mode == "semantic":
            raise
        outcome = search_jobs(db, query, mode="keyword", limit=max(1, min(limit, 20)))
    return {
        "query": query,
        "mode": mode,
        "warnings": outcome.warnings,
        "results": [_job_result(result, profile) for result in outcome.results],
    }


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    db: Session,
    profile: CandidateProfile,
) -> dict[str, Any]:
    """Validate tool input and execute a deterministic application service."""
    try:
        if name in {"search_jobs", "semantic_search", "hybrid_search"}:
            query = str(arguments.get("query", "")).strip()
            if not query:
                raise ValueError("Search query cannot be blank.")
            mode = {
                "semantic_search": "semantic",
                "hybrid_search": "hybrid",
            }.get(name, str(arguments.get("mode", "hybrid")))
            return _search(db, profile, query, mode, int(arguments.get("limit", 10)))

        if name == "get_candidate_profile":
            return ProfileUpdate.model_validate(profile, from_attributes=True).model_dump(mode="json")

        if name == "update_candidate_profile":
            changes = ProfileUpdate.model_validate(arguments).model_dump(exclude_unset=True)
            for key, value in changes.items():
                setattr(profile, key, value)
            db.commit()
            db.refresh(profile)
            return {"updated_fields": sorted(changes)}

        if name == "retrieve_memories":
            query = str(arguments.get("query", "")).casefold()
            context = get_candidate_context(db, profile.id)
            memories = context.get("memories", {})
            selected = {
                key: value for key, value in memories.items()
                if query in key or query in str(value).casefold()
            } if isinstance(memories, dict) else {}
            return {"memories": selected}

        if name == "update_memory":
            memory = MemoryWrite.model_validate(arguments)
            result = update_memory(
                db, profile.id, kind=memory.kind, key=memory.key,
                value=memory.value, is_explicit=memory.is_explicit,
            )
            db.commit()
            return {"updated": result is not None, "key": memory.key}

        if name == "recommend_jobs":
            context = get_candidate_context(db, profile.id)
            memories = context.get("memories", {})
            query_parts = [
                *(profile.skills or []), *(profile.preferred_roles or []),
                profile.career_interests or "",
            ]
            query = " ".join(item for item in query_parts if item)
            if not query:
                return {"results": [], "message": "Complete the profile to get recommendations."}
            result = _search(db, profile, query, "hybrid", int(arguments.get("limit", 10)))
            if isinstance(memories, dict):
                locations = memories.get("preferred_locations")
                if locations:
                    accepted = locations if isinstance(locations, list) else [locations]
                    result["results"] = [
                        item for item in result["results"]
                        if any(str(location).casefold() in
                               str(item["job"].get("location") or "").casefold()
                               for location in accepted)
                    ]
            return result

        if name == "get_similar_jobs":
            job = db.get(Job, str(arguments["job_id"]))
            if job is None:
                return {"error": "Job not found."}
            return _search(
                db, profile, searchable_text(job), "hybrid",
                int(arguments.get("limit", 10)),
            )

        if name == "save_job":
            job_id = str(arguments["job_id"])
            if db.get(Job, job_id) is None:
                return {"error": "Job not found."}
            saved = db.scalar(select(SavedJob).where(
                SavedJob.profile_id == profile.id, SavedJob.job_id == job_id
            ))
            if saved is None:
                db.add(SavedJob(profile_id=profile.id, job_id=job_id))
                db.commit()
            return {"saved": True, "job_id": job_id}

        if name == "record_feedback":
            payload = FeedbackWrite.model_validate(arguments)
            if db.get(Job, payload.job_id) is None:
                return {"error": "Job not found."}
            db.add(JobFeedback(
                profile_id=profile.id, job_id=payload.job_id, feedback=payload.feedback
            ))
            db.commit()
            return {"recorded": True, "feedback": payload.feedback}

        if name == "get_saved_jobs":
            jobs = db.scalars(
                select(Job).join(SavedJob, SavedJob.job_id == Job.id)
                .where(SavedJob.profile_id == profile.id)
                .order_by(SavedJob.created_at.desc())
            )
            return {"jobs": [JobOut.model_validate(job).model_dump(mode="json") for job in jobs]}
        return {"error": f"Unknown tool: {name}"}
    except (ValidationError, ValueError, TypeError) as error:
        db.rollback()
        return {"error": str(error)}
    except Exception:
        db.rollback()
        logger.exception("Career assistant tool execution failed: %s", name)
        return {"error": "Tool execution failed. Check application logs for details."}
