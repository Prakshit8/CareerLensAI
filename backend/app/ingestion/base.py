"""Interfaces and result types shared by ingestion sources."""

from dataclasses import dataclass, field
from typing import Any, Protocol


class JobSource(Protocol):
    """A source that yields raw job records with stable source attribution."""

    source_name: str

    def iter_records(self) -> list[dict[str, Any]]:
        """Return source records; implementations should raise on source I/O errors."""


@dataclass
class ImportReport:
    """Counts and record-level validation failures from a batch import."""

    source: str
    total: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class IngestionError(RuntimeError):
    """Raised when an ingestion source cannot be read."""
