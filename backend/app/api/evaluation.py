"""Read-only evaluation report endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database.connection import get_db
from backend.app.database.models import EvaluationRun

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("/runs")
def list_evaluation_runs(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    runs = db.scalars(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(20)
    )
    return [
        {
            "id": run.id,
            "dataset_name": run.dataset_name,
            "metrics": run.metrics,
            "created_at": run.created_at.isoformat(),
        }
        for run in runs
    ]
