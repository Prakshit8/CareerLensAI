"""JSON ingestion source implementation."""

import json
import logging
from pathlib import Path
from typing import Any

from backend.app.ingestion.base import IngestionError

logger = logging.getLogger(__name__)


class JSONJobSource:
    """Read job records from a JSON array or an object containing a jobs array."""

    def __init__(self, path: Path, source_name: str = "json-import") -> None:
        self.path = path
        self.source_name = source_name

    def iter_records(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            raise IngestionError(f"JSON file not found: {self.path}")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            logger.exception("Could not read jobs JSON at %s", self.path)
            raise IngestionError(f"Could not read jobs JSON: {error}") from error
        records = data.get("jobs") if isinstance(data, dict) else data
        if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
            raise IngestionError("JSON must contain a list of job objects or a 'jobs' list.")
        return records
