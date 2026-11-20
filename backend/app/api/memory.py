"""Persistent candidate memory endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database.connection import get_db
from backend.app.database.models import CandidateMemory
from backend.app.database.schemas import MemoryOut, MemoryWrite
from backend.app.services.profiles import (
    delete_memory, get_candidate_profile, retrieve_memories, save_memory,
)

router = APIRouter(prefix="/api/memories", tags=["memory"])


@router.get("", response_model=list[MemoryOut])
def list_memories(db: Session = Depends(get_db)) -> list[CandidateMemory]:
    profile = get_candidate_profile(db)
    return retrieve_memories(db, profile.id)


@router.put("", response_model=MemoryOut)
def put_memory(payload: MemoryWrite, db: Session = Depends(get_db)) -> CandidateMemory:
    profile = get_candidate_profile(db)
    memory = save_memory(
        db, profile.id, kind=payload.kind, key=payload.key,
        value=payload.value, is_explicit=payload.is_explicit,
    )
    db.commit()
    if memory is None:
        raise HTTPException(status_code=500, detail="Memory update failed.")
    db.refresh(memory)
    return memory


@router.delete("/{memory_id}", status_code=204)
def remove_memory(memory_id: int, db: Session = Depends(get_db)) -> None:
    profile = get_candidate_profile(db)
    memory = db.get(CandidateMemory, memory_id)
    if memory is None or memory.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Memory not found.")
    delete_memory(db, profile.id, memory_id)
    db.commit()
