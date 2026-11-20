"""Explainable weighted candidate-job scoring."""

from dataclasses import dataclass
from typing import Any

from backend.app.database.models import CandidateProfile, Job
from backend.app.search.vector import searchable_text

DEFAULT_WEIGHTS = {
    "semantic": 0.38,
    "skills": 0.25,
    "experience": 0.15,
    "location": 0.10,
    "preferences": 0.08,
    "salary": 0.04,
}

LEVEL_ORDER = {
    "intern": 0, "internship": 0, "entry": 0, "entry-level": 0, "fresher": 0,
    "junior": 1, "mid": 2, "mid-level": 2, "senior": 3, "lead": 4,
}


@dataclass
class RecommendationScore:
    score: float
    components: dict[str, float | None]
    explanation: list[str]
    eligible: bool | None


def _level(value: str | None) -> int | None:
    if not value:
        return None
    folded = value.casefold()
    return next((rank for label, rank in LEVEL_ORDER.items() if label in folded), None)


def score_job(
    job: Job,
    profile: CandidateProfile,
    retrieval: dict[str, Any],
    feedback: str | None = None,
    weights: dict[str, float] | None = None,
) -> RecommendationScore:
    """Score only known dimensions, renormalizing weights over available evidence."""
    weights = weights or DEFAULT_WEIGHTS
    components: dict[str, float | None] = {
        "semantic": retrieval.get("semantic_score"),
        "skills": None,
        "experience": None,
        "location": None,
        "preferences": None,
        "salary": None,
    }
    explanations: list[str] = []
    job_skills = {skill.casefold() for skill in job.skills or []}
    candidate_skills = {skill.casefold() for skill in profile.skills or []}
    matched_skills = sorted(candidate_skills & job_skills)
    if candidate_skills and job_skills:
        components["skills"] = len(matched_skills) / len(candidate_skills)
        if matched_skills:
            explanations.append("Matching skills: " + ", ".join(matched_skills))

    candidate_level = _level(profile.experience_level)
    job_level = _level(job.experience_level)
    eligible: bool | None = None
    if candidate_level is not None and job_level is not None:
        eligible = candidate_level >= job_level
        components["experience"] = 1.0 if eligible else 0.0
        if eligible:
            explanations.append(f"Experience level is compatible ({job.experience_level}).")
        else:
            explanations.append(f"Role asks for {job.experience_level}; check eligibility.")

    if profile.preferred_locations and job.location:
        job_location = job.location.casefold()
        is_remote = any(term in job_location for term in ("remote", "anywhere", "work from home"))
        matched_location = any(
            pref.casefold() in job_location or (
                pref.casefold() == "remote" and is_remote
            )
            for pref in profile.preferred_locations
        )
        components["location"] = float(matched_location)
        if matched_location:
            explanations.append(f"Location matches your preference ({job.location}).")

    preference_parts: list[float] = []
    job_text = searchable_text(job).casefold()
    if profile.preferred_roles:
        role_matches = [
            role for role in profile.preferred_roles
            if role.casefold() in job_text
        ]
        preference_parts.append(float(bool(role_matches)))
        if role_matches:
            explanations.append("Role matches: " + ", ".join(role_matches))
    if profile.preferred_employment_types and job.employment_type:
        employment_match = any(
            item.casefold() in job.employment_type.casefold()
            for item in profile.preferred_employment_types
        )
        preference_parts.append(float(employment_match))
        if employment_match:
            explanations.append(f"Matches preferred employment type ({job.employment_type}).")
    if preference_parts:
        components["preferences"] = sum(preference_parts) / len(preference_parts)

    if (
        (profile.salary_min is not None or profile.salary_max is not None)
        and (job.salary_min is not None or job.salary_max is not None)
    ):
        lower_bound = profile.salary_min
        upper_bound = profile.salary_max
        job_lower = job.salary_min
        job_upper = job.salary_max
        overlaps = (
            (upper_bound is None or job_lower is None or job_lower <= upper_bound)
            and (lower_bound is None or job_upper is None or job_upper >= lower_bound)
        )
        components["salary"] = float(overlaps)
        if overlaps:
            explanations.append("Known salary range overlaps your stated expectations.")

    known = [
        (name, value, weights.get(name, 0.0))
        for name, value in components.items()
        if value is not None and weights.get(name, 0.0) > 0
    ]
    denominator = sum(weight for _, _, weight in known)
    score = sum(float(value) * weight for _, value, weight in known) / denominator if denominator else 0.0
    if feedback == "like":
        score = min(1.0, score + 0.05)
        explanations.append("Previously liked.")
    elif feedback in {"dislike", "not_relevant"}:
        score = max(0.0, score - 0.25)
    if not explanations:
        explanations.append("Ranked from available search and profile information.")
    return RecommendationScore(score, components, explanations, eligible)
