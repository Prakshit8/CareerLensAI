"""Environment-based application settings."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Validated runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CareerLens AI"
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'careerlens.db').as_posix()}"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    vector_index_dir: Path = PROJECT_ROOT / "data" / "indexes"
    demo_identity: str = "local-demo"
    rrf_constant: int = 60
    recommendation_weights: dict[str, float] = {
        "semantic": 0.38,
        "skills": 0.25,
        "experience": 0.15,
        "location": 0.10,
        "preferences": 0.08,
        "salary": 0.04,
    }

    @field_validator("recommendation_weights")
    @classmethod
    def validate_recommendation_weights(cls, value: dict[str, float]) -> dict[str, float]:
        if not value or any(weight < 0 for weight in value.values()) or sum(value.values()) <= 0:
            raise ValueError("Recommendation weights must be non-negative with a positive sum.")
        return value


settings = Settings()
if not settings.database_url.startswith("sqlite:///"):
    raise RuntimeError("CareerLens AI uses SQLite; configure DATABASE_URL with a sqlite:/// URL.")
