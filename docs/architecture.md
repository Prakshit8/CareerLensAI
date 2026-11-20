# CareerLens AI architecture

## Runtime

- **FastAPI** validates requests and exposes job, profile, search, memory, feedback, assistant, and evaluation endpoints.
- **SQLite + SQLAlchemy** persist listings, the local demo candidate, memories, conversations, search history, feedback, saved jobs, and evaluation runs.
- **BM25** provides an always-available lexical baseline without a model download.
- **Sentence Transformers** loads `all-MiniLM-L6-v2` lazily on CPU. Normalized vectors are indexed in FAISS and persisted under `data/indexes/`; an ID/hash manifest prevents stale mappings. New jobs can be appended; changed or removed records cause a rebuild.
- **Hybrid retrieval** merges BM25 and dense rankings by reciprocal rank fusion. If the embedding package/model is unavailable, hybrid mode explicitly reports that it used BM25 only; semantic-only requests return HTTP 503 rather than claiming semantic results.
- **Recommendation ranking** applies configurable weighted scores to known evidence only. Missing dimensions are excluded and remaining weights are renormalized. Explanations cite matched skills, role, preference, or eligibility evidence.
- **Career assistant** uses Groq function calling when `GROQ_API_KEY` is configured. Python validates and executes every tool. A deterministic local search/preference path remains available without the key.
- **Streamlit** is a separate dashboard process and connects to the API through `CAREERLENS_API_URL`.

## Data flow

1. A CSV/JSON source is normalized and validated.
2. Jobs are upserted by `(source, external_id)` with deterministic IDs.
3. Search applies active-listing and user filters before retrieval.
4. Search results retain component scores/ranks and are personalized from the local candidate profile.
5. Explicit preferences and interactions persist in SQLite and are reused on follow-up searches.

## Boundaries and privacy

- This build is a single-user local demo; it does not provide authentication or multi-tenant access control.
- Resume text is stored only after upload and is not sent to Groq as part of default context.
- The Groq assistant receives a small candidate context, not the database or resume.
- Synthetic data is marked in every record and must not be presented as live vacancies.
- No job-board scraping or unapproved third-party collection is implemented.
