"""Bounded Groq tool orchestration and deterministic offline fallback."""

import json
import logging
import re
import time
from typing import Any
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent.tools import GROQ_TOOLS, execute_tool
from backend.app.config import settings
from backend.app.database.models import (
    AgentToolRun, CandidateMemory, CandidateProfile, Conversation,
    ConversationMessage, SearchHistory,
)
from backend.app.search.service import search_jobs
from backend.app.services.profiles import (
    get_candidate_context, record_search_history, update_memory,
)

logger = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 4


class CareerAssistant:
    """Persist chat exchanges and use bounded, validated function calls."""

    def __init__(self, db: Session, profile: CandidateProfile) -> None:
        self.db = db
        self.profile = profile

    def _conversation(self, conversation_id: int | None, title: str) -> Conversation:
        if conversation_id is not None:
            conversation = self.db.get(Conversation, conversation_id)
            if conversation is None or conversation.profile_id != self.profile.id:
                raise ValueError("Conversation not found.")
            return conversation
        conversation = Conversation(profile_id=self.profile.id, title=title[:200])
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def respond(self, message: str, conversation_id: int | None = None) -> dict[str, Any]:
        conversation = self._conversation(conversation_id, message)
        conversation.updated_at = datetime.now(timezone.utc)
        self.db.add(ConversationMessage(
            conversation_id=conversation.id, role="user", content=message
        ))
        self.db.commit()
        if settings.groq_api_key:
            try:
                result = self._groq_reply(conversation, message)
                result["llm_used"] = True
            except Exception:
                logger.exception("Groq assistant request failed; using local search fallback")
                result = self._local_reply(message)
                result["reply"] = (
                    "I couldn't reach the assistant service, so I used local job search. "
                    + result["reply"]
                )
                result["llm_used"] = False
        else:
            result = self._local_reply(message)
            result["llm_used"] = False
        self.db.add(ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=result["reply"],
        ))
        self.db.commit()
        result["conversation_id"] = conversation.id
        return result

    def _groq_reply(self, conversation: Conversation, message: str) -> dict[str, Any]:
        from groq import Groq

        context = get_candidate_context(self.db, self.profile.id)
        memories = context.get("memories", {})
        relevant_memory_keys = {
            "preferred_locations", "preferred_roles",
            "preferred_employment_types", "career_interests",
        }
        safe_context = {
            "skills": self.profile.skills,
            "experience_level": self.profile.experience_level,
            "preferred_roles": self.profile.preferred_roles,
            "preferred_locations": self.profile.preferred_locations,
            "memories": {
                key: value for key, value in memories.items()
                if key in relevant_memory_keys
            } if isinstance(memories, dict) else {},
        }
        recent = list(self.db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
            .limit(8)
        ))
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are CareerLens, a career search assistant. Use tools for job facts, "
                    "profile changes, memory, recommendations, saves, and feedback. Never invent "
                    "jobs, matches, or scores. Ask before changing profile data unless the user "
                    "clearly stated the preference. Clearly disclose when returned listings are "
                    "synthetic demo data; never call them live or real vacancies, and never imply "
                    "a live job feed exists. Keep replies concise. Relevant candidate "
                    f"context: {json.dumps(safe_context, ensure_ascii=True)}"
                ),
            }
        ]
        messages.extend(
            {"role": item.role, "content": item.content}
            for item in reversed(recent) if item.role in {"user", "assistant"}
        )
        if not recent or recent[0].role != "user" or recent[0].content != message:
            messages.append({"role": "user", "content": message})

        client = Groq(api_key=settings.groq_api_key, timeout=30.0, max_retries=1)
        tool_names: list[str] = []
        job_results: list[dict[str, Any]] = []
        for _ in range(MAX_TOOL_ROUNDS):
            completion = client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                tools=GROQ_TOOLS,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=900,
            )
            response = completion.choices[0].message
            if not response.tool_calls:
                return {
                    "reply": response.content or "I couldn't find a response for that request.",
                    "results": job_results,
                    "tool_calls": tool_names,
                }
            messages.append(response.model_dump(exclude_none=True))
            for tool_call in response.tool_calls:
                tool_name = tool_call.function.name
                tool_names.append(tool_name)
                logger.info("Executing CareerLens assistant tool: %s", tool_name)
                tool_started = time.perf_counter()
                try:
                    arguments = json.loads(tool_call.function.arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be a JSON object.")
                    output = execute_tool(tool_name, arguments, self.db, self.profile)
                except (json.JSONDecodeError, ValueError) as error:
                    output = {"error": f"Invalid tool arguments: {error}"}
                self.db.add(AgentToolRun(
                    profile_id=self.profile.id,
                    conversation_id=conversation.id,
                    tool_name=tool_name,
                    success="error" not in output,
                    latency_ms=(time.perf_counter() - tool_started) * 1000,
                ))
                if isinstance(output.get("results"), list):
                    job_results.extend(output["results"])
                self.db.add(ConversationMessage(
                    conversation_id=conversation.id,
                    role="tool",
                    tool_name=tool_name,
                    content=json.dumps(output, ensure_ascii=True, default=str)[:12000],
                ))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(output, ensure_ascii=True, default=str)[:12000],
                })
            self.db.commit()
        return {
            "reply": "I reached the assistant's tool-use limit. Please narrow or restate the request.",
            "results": job_results,
            "tool_calls": tool_names,
        }

    def _local_reply(self, message: str) -> dict[str, Any]:
        folded = message.casefold()
        remote_requested = bool(re.search(r"\b(remote|work from home|wfh)\b", folded))
        preference_intent = bool(re.search(r"\b(prefer|only|want|looking for|filter)\b", folded))
        remove_remote = bool(re.search(
            r"\b(remove|forget|no longer|don't|do not|not looking for|stop)\b", folded
        ))
        if remote_requested and preference_intent and remove_remote:
            memory = self.db.scalar(select(CandidateMemory).where(
                CandidateMemory.profile_id == self.profile.id,
                CandidateMemory.key == "preferred_locations",
            ))
            if memory:
                self.db.delete(memory)
                self.profile.preferred_locations = [
                    location for location in (self.profile.preferred_locations or [])
                    if location.casefold() != "remote"
                ]
                self.db.commit()
            return {
                "reply": "I removed your saved remote-location preference.",
                "results": [], "tool_calls": ["update_memory"],
            }

        updated_preference = False
        if remote_requested and preference_intent:
            update_memory(
                self.db, self.profile.id, kind="preference",
                key="preferred_locations", value=["Remote"], is_explicit=True,
            )
            if "Remote" not in (self.profile.preferred_locations or []):
                self.profile.preferred_locations = [
                    *(self.profile.preferred_locations or []), "Remote"
                ]
            self.db.commit()
            updated_preference = True

        previous = self.db.scalar(
            select(SearchHistory)
            .where(SearchHistory.profile_id == self.profile.id)
            .order_by(SearchHistory.created_at.desc())
        )
        continuation = bool(re.search(r"\b(more|again|next|similar)\b", folded))
        if continuation and previous:
            query = previous.query
        else:
            query = re.sub(
                r"^(find|search for|search|show me|show|look for)\s+",
                "", message.strip(), flags=re.IGNORECASE,
            )
            query = re.sub(
                r"\b(only show( me)?|prefer|looking for)\s+(remote|work from home|wfh)\b",
                "", query, flags=re.IGNORECASE,
            ).strip(" ,.!?")
            if updated_preference and previous:
                query = previous.query
            if not query or query.casefold() in {
                "more", "me more", "jobs", "opportunities", "remote opportunities",
            }:
                query = " ".join([
                    *(self.profile.skills or []), *(self.profile.preferred_roles or []),
                    self.profile.career_interests or "",
                ]).strip()
        if not query:
            return {
                "reply": (
                    "Tell me a role or skill to search for, or add skills and career interests "
                    "to your profile."
                ),
                "results": [], "tool_calls": [],
            }

        memories = get_candidate_context(self.db, self.profile.id).get("memories", {})
        location_filter = None
        if isinstance(memories, dict):
            remembered = memories.get("preferred_locations")
            if remembered:
                location_filter = (
                    remembered[0] if isinstance(remembered, list) and remembered
                    else str(remembered)
                )
        if remote_requested and not preference_intent:
            location_filter = "Remote"
        started = time.perf_counter()
        outcome = search_jobs(
            self.db, query, mode="hybrid", limit=10, location=location_filter
        )
        latency_ms = (time.perf_counter() - started) * 1000
        from backend.app.database.schemas import JobOut

        results = [
            {
                "job": JobOut.model_validate(item.job).model_dump(mode="json"),
                "score": item.score,
                "explanation": [
                    "Retrieved using semantic and keyword evidence."
                    if item.retrieval.get("semantic_score") is not None
                    else "Retrieved using keyword matching."
                ],
                "retrieval": item.retrieval,
            }
            for item in outcome.results
        ]
        record_search_history(
            self.db, self.profile.id, query=query, mode="hybrid",
            filters={"location": location_filter} if location_filter else {},
            result_count=len(results), latency_ms=latency_ms,
        )
        self.db.commit()
        if results:
            reply = f"I found {len(results)} matching job listings."
        else:
            reply = "I didn't find matching active listings. Try different skills or a broader role."
        if updated_preference:
            reply = "I saved your remote preference. " + reply
        if outcome.warnings:
            reply += " Semantic search is unavailable, so these results use keyword matching."
        return {
            "reply": reply, "results": results,
            "tool_calls": ["hybrid_search"] + (["update_memory"] if updated_preference else []),
        }
