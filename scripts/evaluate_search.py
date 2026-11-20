"""Run labeled retrieval benchmarks and write reproducible JSON and CSV reports."""

import csv
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from backend.app.config import PROJECT_ROOT, settings
from backend.app.database import models  # noqa: F401
from backend.app.database.connection import Base, SessionLocal, engine
from backend.app.database.models import AgentToolRun, CandidateProfile, EvaluationRun, Job
from backend.app.evaluation.agent_metrics import tool_execution_success_rate
from backend.app.evaluation.metrics import retrieval_metrics
from backend.app.search.service import SearchOutcome, search_jobs
from backend.app.search.vector import SemanticSearchUnavailable
from backend.app.ranking.scorer import score_job


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def main() -> None:
    dataset_path = PROJECT_ROOT / "data" / "evaluation" / "queries.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    output_dir = PROJECT_ROOT / "data" / "evaluation" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    all_rows: list[dict[str, object]] = []
    summary: dict[str, dict[str, object]] = {}
    errors: dict[str, list[str]] = {}
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        jobs = list(db.scalars(select(Job)))
        by_external_id = {job.external_id: job for job in jobs}
        profile = db.scalar(select(CandidateProfile).limit(1))
        if profile is None:
            profile = CandidateProfile(identity=settings.demo_identity)
            db.add(profile)
            db.commit()
        modes = ("keyword", "semantic", "hybrid", "personalized")

        for mode in modes:
            query_rows = []
            latencies: list[float] = []
            failed = 0
            warnings: list[str] = []
            for case in dataset["queries"]:
                missing = [
                    external_id for external_id in case["relevant_external_ids"]
                    if external_id not in by_external_id
                ]
                if missing:
                    failed += 1
                    errors.setdefault(mode, []).append(
                        f"{case['query']}: missing labeled job IDs: {', '.join(missing)}"
                    )
                    continue
                relevant = {
                    external_id: 1 for external_id in case["relevant_external_ids"]
                }
                retrieval_mode = "hybrid" if mode == "personalized" else mode
                started = datetime.now(timezone.utc)
                try:
                    outcome: SearchOutcome = search_jobs(
                        db, case["query"], mode=retrieval_mode, limit=20
                    )
                    if mode == "personalized":
                        candidate = SimpleNamespace(
                            skills=case.get("profile", {}).get("skills", []),
                            experience_level=case.get("profile", {}).get("experience_level"),
                            preferred_roles=case.get("profile", {}).get("preferred_roles", []),
                            preferred_locations=case.get("profile", {}).get("preferred_locations", []),
                            preferred_employment_types=case.get("profile", {}).get(
                                "preferred_employment_types", []
                            ),
                            salary_min=None,
                            salary_max=None,
                            career_interests=case.get("profile", {}).get("career_interests"),
                        )
                        outcome.results.sort(
                            key=lambda result: (
                                -score_job(result.job, candidate, result.retrieval,
                                           weights=settings.recommendation_weights).score,
                                result.job.id,
                            )
                        )
                    warnings.extend(outcome.warnings)
                except SemanticSearchUnavailable as error:
                    failed += 1
                    errors.setdefault(mode, []).append(f"{case['query']}: {error}")
                    continue
                elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000
                latencies.append(elapsed)
                ranked_ids = [result.job.external_id for result in outcome.results]
                metrics = retrieval_metrics(ranked_ids, relevant)
                row = {"mode": mode, "query": case["query"], **metrics, "latency_ms": elapsed}
                all_rows.append(row)
                query_rows.append(metrics)

            keys = query_rows[0].keys() if query_rows else ()
            summary[mode] = {
                "queries_succeeded": len(query_rows),
                "queries_total": len(dataset["queries"]),
                "metrics": {
                    key: statistics.mean(item[key] for item in query_rows)
                    for key in keys
                },
                "latency_ms": {
                    "p50": _percentile(latencies, 0.50),
                    "p95": _percentile(latencies, 0.95),
                },
                "error_rate": failed / max(len(dataset["queries"]), 1),
                "warnings": sorted(set(warnings)),
                "errors": errors.get(mode, []),
            }

        tool_runs = list(db.scalars(select(AgentToolRun)))
        report = {
            "dataset": dataset["name"],
            "label_method": dataset["label_method"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "agent_metrics": {
                "tool_selection_accuracy": None,
                "tool_execution_success_rate": tool_execution_success_rate([
                    run.success for run in tool_runs
                ]),
                "task_completion_rate": None,
                "preference_retention_accuracy": None,
                "tool_execution_count": len(tool_runs),
                "note": (
                    "Tool execution success is computed from persisted tool traces. "
                    "Selection, task completion, and preference retention require labeled "
                    "agent scenarios and are not inferred from unlabelled conversations."
                ),
            },
        }
        json_path = output_dir / f"search-evaluation-{timestamp}.json"
        csv_path = output_dir / f"search-evaluation-{timestamp}.csv"
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8") as file:
            columns = list(all_rows[0]) if all_rows else [
                "mode", "query", "mrr", "precision@5", "recall@5",
                "hit_rate@5", "ndcg@5", "precision@10", "recall@10",
                "hit_rate@10", "ndcg@10", "latency_ms",
            ]
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(all_rows)
        db.add(EvaluationRun(dataset_name=dataset["name"], metrics=report))
        db.commit()

    print(json.dumps({"json_report": str(json_path), "csv_report": str(csv_path),
                      "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
