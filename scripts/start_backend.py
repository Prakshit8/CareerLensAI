"""Render/startup entry point that seeds demo data and runs Uvicorn."""

import os
import sys

from scripts.seed_database import main as seed_database


def main() -> None:
    port = os.getenv("PORT", "8000")
    sys.argv = ["seed_database"]
    seed_database()
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
        ],
    )


if __name__ == "__main__":
    main()
