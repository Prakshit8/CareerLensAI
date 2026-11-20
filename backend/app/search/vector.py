"""Lazy Sentence Transformers + FAISS semantic retrieval with persisted indices."""

import hashlib
import json
import logging
from pathlib import Path

from backend.app.config import settings
from backend.app.database.models import Job

logger = logging.getLogger(__name__)


class SemanticSearchUnavailable(RuntimeError):
    """Raised when the embedding model or FAISS cannot be loaded."""


def searchable_text(job: Job) -> str:
    return "\n".join(
        part for part in (
            job.title, job.role_category or "", job.description,
            " ".join(job.skills or []), job.experience_level or "",
            job.employment_type or "", job.location or "",
        ) if part
    )


class SemanticIndex:
    """Build and persist a cosine-similarity FAISS index for active jobs."""

    def __init__(self) -> None:
        self._model = None
        self._faiss = None
        self._model_error: str | None = None

    def _dependencies(self):
        try:
            from sentence_transformers import SentenceTransformer
            import faiss
        except ImportError as error:
            raise SemanticSearchUnavailable(
                "Semantic search requires sentence-transformers and faiss-cpu."
            ) from error
        if self._model is None:
            if self._model_error:
                raise SemanticSearchUnavailable(self._model_error)
            try:
                self._model = SentenceTransformer(settings.embedding_model, device="cpu")
            except Exception as error:
                logger.exception("Could not load embedding model %s", settings.embedding_model)
                self._model_error = (
                    f"Could not load embedding model '{settings.embedding_model}'. "
                    "Check model access or use keyword search."
                )
                raise SemanticSearchUnavailable(self._model_error) from error
        self._faiss = faiss
        return self._model, faiss

    @staticmethod
    def _fingerprint(jobs: list[Job]) -> tuple[list[str], list[str]]:
        job_ids = [job.id for job in jobs]
        hashes = [
            hashlib.sha256(searchable_text(job).encode("utf-8")).hexdigest()
            for job in jobs
        ]
        return job_ids, hashes

    def _load_or_build(self, jobs: list[Job]):
        model, faiss = self._dependencies()
        job_ids, hashes = self._fingerprint(jobs)
        index_dir = settings.vector_index_dir
        index_dir.mkdir(parents=True, exist_ok=True)
        index_path = index_dir / "jobs.faiss"
        manifest_path = index_dir / "jobs.json"
        manifest = None
        if index_path.is_file() and manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("model") == settings.embedding_model:
                    old_ids = manifest.get("job_ids", [])
                    old_hashes = manifest.get("hashes", [])
                    current_hashes = dict(zip(job_ids, hashes))
                    old_is_current = (
                        len(old_ids) == len(old_hashes)
                        and all(
                            job_id in current_hashes
                            and current_hashes[job_id] == old_hash
                            for job_id, old_hash in zip(old_ids, old_hashes)
                        )
                    )
                    if old_is_current and old_ids != job_ids:
                        index = faiss.read_index(str(index_path))
                        old_set = set(old_ids)
                        additions = [job for job in jobs if job.id not in old_set]
                        if additions:
                            vectors = model.encode(
                                [searchable_text(job) for job in additions],
                                normalize_embeddings=True,
                                convert_to_numpy=True,
                                show_progress_bar=False,
                            ).astype("float32")
                            index.add(vectors)
                        combined_ids = [*old_ids, *(job.id for job in additions)]
                        combined_hashes = [
                            *old_hashes, *(current_hashes[job_id] for job_id in combined_ids[len(old_ids):])
                        ]
                        faiss.write_index(index, str(index_path.with_suffix(".faiss.tmp")))
                        manifest_path.with_suffix(".json.tmp").write_text(
                            json.dumps({
                                "model": settings.embedding_model,
                                "job_ids": combined_ids,
                                "hashes": combined_hashes,
                            }),
                            encoding="utf-8",
                        )
                        index_path.with_suffix(".faiss.tmp").replace(index_path)
                        manifest_path.with_suffix(".json.tmp").replace(manifest_path)
                        return index, combined_ids
                if (
                    manifest.get("model") == settings.embedding_model
                    and manifest.get("job_ids") == job_ids
                    and manifest.get("hashes") == hashes
                ):
                    return faiss.read_index(str(index_path)), job_ids
            except (OSError, ValueError, RuntimeError):
                logger.warning("Persisted vector index is invalid; rebuilding it.")

        if not jobs:
            return faiss.IndexFlatIP(384), job_ids
        try:
            vectors = model.encode(
                [searchable_text(job) for job in jobs],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            vectors = vectors.astype("float32")
            index = faiss.IndexFlatIP(vectors.shape[1])
            index.add(vectors)
            temporary_index = index_dir / "jobs.faiss.tmp"
            temporary_manifest = index_dir / "jobs.json.tmp"
            faiss.write_index(index, str(temporary_index))
            temporary_manifest.write_text(
                json.dumps({
                    "model": settings.embedding_model,
                    "job_ids": job_ids,
                    "hashes": hashes,
                }),
                encoding="utf-8",
            )
            temporary_index.replace(index_path)
            temporary_manifest.replace(manifest_path)
            return index, job_ids
        except Exception as error:
            logger.exception("Could not build the semantic job index")
            raise SemanticSearchUnavailable("Could not build the semantic search index.") from error

    def search(self, query: str, jobs: list[Job], limit: int) -> dict[str, float]:
        if not query.strip():
            raise ValueError("Semantic search query cannot be blank.")
        if limit <= 0:
            raise ValueError("Semantic search limit must be positive.")
        if not jobs:
            return {}
        model, _ = self._dependencies()
        index, job_ids = self._load_or_build(jobs)
        try:
            query_vector = model.encode(
                [query], normalize_embeddings=True, convert_to_numpy=True,
                show_progress_bar=False,
            ).astype("float32")
            scores, indices = index.search(query_vector, min(limit, len(job_ids)))
        except Exception as error:
            logger.exception("Semantic query encoding or retrieval failed")
            raise SemanticSearchUnavailable("Could not run semantic retrieval.") from error
        return {
            job_ids[index_value]: max(0.0, min(1.0, float(score)))
            for score, index_value in zip(scores[0], indices[0])
            if index_value >= 0
        }

    def build(self, jobs: list[Job]) -> int:
        """Create or refresh the persisted index and return the indexed job count."""
        self._load_or_build(jobs)
        return len(jobs)


semantic_index = SemanticIndex()
