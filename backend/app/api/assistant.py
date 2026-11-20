"""Persistent career assistant chat endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent.service import CareerAssistant
from backend.app.database.connection import get_db
from backend.app.database.models import Conversation, ConversationMessage
from backend.app.database.schemas import AssistantRequest, AssistantResponse
from backend.app.services.profiles import get_candidate_profile

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/chat", response_model=AssistantResponse)
def chat(payload: AssistantRequest, db: Session = Depends(get_db)) -> AssistantResponse:
    profile = get_candidate_profile(db)
    assistant = CareerAssistant(db, profile)
    try:
        result = assistant.respond(payload.message.strip(), payload.conversation_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return AssistantResponse.model_validate(result)


@router.get("/conversations")
def conversations(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    profile = get_candidate_profile(db)
    rows = db.scalars(
        select(Conversation).where(Conversation.profile_id == profile.id)
        .order_by(Conversation.updated_at.desc())
    )
    return [
        {"id": item.id, "title": item.title, "created_at": item.created_at.isoformat(),
         "updated_at": item.updated_at.isoformat()}
        for item in rows
    ]


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    profile = get_candidate_profile(db)
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    return [
        {"role": item.role, "content": item.content, "tool_name": item.tool_name,
         "created_at": item.created_at.isoformat()}
        for item in messages
    ]
