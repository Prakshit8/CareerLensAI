"""Validated request and response schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class JobCreate(BaseModel):
    external_id: str | None = None
    source: str = "manual"
    title: str = Field(min_length=1, max_length=300)
    company: str = Field(default="Undisclosed", max_length=300)
    description: str = ""
    location: str | None = None
    employment_type: str | None = None
    experience_level: str | None = None
    role_category: str | None = None
    skills: list[str] = Field(default_factory=list)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    apply_url: str | None = None
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    is_synthetic: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title cannot be blank.")
        return value

    @field_validator("source")
    @classmethod
    def clean_source(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source cannot be blank.")
        return value

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(skill.strip() for skill in value if skill.strip()))

    @model_validator(mode="after")
    def validate_salary_range(self) -> "JobCreate":
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_max < self.salary_min:
                raise ValueError("salary_max cannot be lower than salary_min.")
        return self


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_id: str
    source: str
    title: str
    company: str
    description: str
    location: str | None
    employment_type: str | None
    experience_level: str | None
    role_category: str | None
    skills: list[str]
    salary_min: float | None
    salary_max: float | None
    apply_url: str | None
    posted_at: datetime | None
    expires_at: datetime | None
    is_synthetic: bool
    created_at: datetime
    updated_at: datetime


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    skills: list[str] | None = None
    experience_level: str | None = None
    education: str | None = None
    preferred_roles: list[str] | None = None
    preferred_locations: list[str] | None = None
    preferred_employment_types: list[str] | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    career_interests: str | None = None
    resume_text: str | None = None

    @model_validator(mode="after")
    def validate_salary_range(self) -> "ProfileUpdate":
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_max < self.salary_min:
                raise ValueError("salary_max cannot be lower than salary_min.")
        return self


class ProfileOut(ProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    identity: str
    skills: list[str]
    preferred_roles: list[str]
    preferred_locations: list[str]
    preferred_employment_types: list[str]
    created_at: datetime
    updated_at: datetime
    completion_status: str


class MemoryWrite(BaseModel):
    kind: str = Field(min_length=1, max_length=50)
    key: str = Field(min_length=1, max_length=150)
    value: Any
    is_explicit: bool = True

    @field_validator("kind", "key")
    @classmethod
    def clean_memory_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Memory kind and key cannot be blank.")
        return value


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    key: str
    value: Any
    is_explicit: bool
    created_at: datetime
    updated_at: datetime


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    location: str | None = None
    role: str | None = None
    experience_level: str | None = None
    employment_type: str | None = None
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def query_must_have_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Search query cannot be blank.")
        return value.strip()


class SearchHit(BaseModel):
    job: JobOut
    score: float
    explanation: list[str] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    mode: str
    results: list[SearchHit]
    filters_applied: dict[str, str]
    warnings: list[str] = Field(default_factory=list)


class FeedbackWrite(BaseModel):
    job_id: str
    feedback: Literal["like", "dislike", "not_relevant", "applied"]


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None


class AssistantResponse(BaseModel):
    conversation_id: int
    reply: str
    results: list[SearchHit] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    llm_used: bool = False
