"""CSV ingestion source implementation."""

import csv
import logging
from pathlib import Path
from typing import Any

from backend.app.ingestion.base import IngestionError

logger = logging.getLogger(__name__)


class CSVJobSource:
    """Read job records from a UTF-8 CSV file."""

    def __init__(self, path: Path, source_name: str = "csv-import") -> None:
        self.path = path
        self.source_name = source_name

    def iter_records(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            raise IngestionError(f"CSV file not found: {self.path}")
        try:
            with self.path.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                if not reader.fieldnames or "title" not in reader.fieldnames:
                    raise IngestionError("CSV must include a 'title' column.")
                return [dict(row) for row in reader]
        except (OSError, UnicodeError, csv.Error) as error:
            logger.exception("Could not read jobs CSV at %s", self.path)
            raise IngestionError(f"Could not read jobs CSV: {error}") from error
