# CareerLens AI

CareerLens AI is a local-first job discovery and recommendation portfolio application. It combines a FastAPI backend, SQLite persistence, BM25 keyword retrieval, CPU sentence embeddings with FAISS, explainable recommendations, persistent candidate preferences, an optional Groq tool-using assistant, and a Streamlit dashboard.

> **Synthetic data notice:** the checked-in demo jobs are fictional examples for local development and evaluation, not real vacancies.

## Features

- Idempotent CSV and JSON job ingestion with validation, stable IDs, source attribution, and batch reports.
- Candidate profile editing, selectable-text PDF extraction, and transparent vocabulary-based skill detection.
- Keyword, semantic, and hybrid search with filters, RRF metadata, and a visible fallback warning if dense retrieval is unavailable.
- Weighted recommendations with match evidence, eligibility status, saved jobs, and persisted feedback.
- SQLite-backed profile preferences, memories, conversations, and search history.
- Optional Groq tool calling; profile, search, memory, recommendation, save, and feedback tools run through validated Python services. Core search does not require an LLM key.
- Reproducible retrieval evaluation producing JSON/CSV reports.
- Streamlit pages for dashboard, search, recommendations, profile, assistant, saved jobs, history, evaluation, and settings.

## Windows setup (CMD)

Run commands from the repository root. Python 3.10+ is supported.

```cmd
py -3.10 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
```

Edit `.env` if needed. `DATABASE_URL` defaults to SQLite. `GROQ_API_KEY` is optional; leave it empty to use local search and preference handling. Never commit `.env` or expose its key in the frontend.

Generate and import the explicitly synthetic demo dataset:

```cmd
python -m scripts.generate_demo_jobs
python -m scripts.seed_database
```

The ingestion command can read either CSV or JSON:

```cmd
python -m scripts.seed_database --input data\raw\jobs.csv --source synthetic-demo
python -m scripts.seed_database --input path\to\jobs.json --source licensed-dataset
```

Build the CPU embedding index (requires internet access the first time to download `all-MiniLM-L6-v2`):

```cmd
python -m scripts.build_index
```

Start the backend and frontend in two separate CMD windows:

```cmd
venv\Scripts\activate
uvicorn backend.app.main:app --reload
```

```cmd
venv\Scripts\activate
streamlit run frontend\app.py
```

Open `http://localhost:8501`; API documentation is at `http://127.0.0.1:8000/docs`.

Run tests and the evaluation benchmark:

```cmd
pytest -q
python -m scripts.evaluate_search
```

The evaluator writes timestamped reports to `data\evaluation\reports` and stores a copy in SQLite. When using PowerShell, activate with `.\venv\Scripts\Activate.ps1`.

## Docker

Create `.env` as above, then:

```cmd
docker compose up --build
```

Open the UI at `http://localhost:8501`. Persistent SQLite data and FAISS files are mounted under `data`.

## API examples

```cmd
curl -X POST http://127.0.0.1:8000/api/search -H "Content-Type: application/json" -d "{\"query\":\"entry-level AI internships with Python and RAG\",\"mode\":\"hybrid\",\"limit\":10}"
curl -X PATCH http://127.0.0.1:8000/api/profiles/me -H "Content-Type: application/json" -d "{\"skills\":[\"Python\",\"RAG\"],\"experience_level\":\"Fresher\",\"preferred_locations\":[\"Remote\"]}"
curl -X POST http://127.0.0.1:8000/api/assistant/chat -H "Content-Type: application/json" -d "{\"message\":\"Only show me remote opportunities\"}"
```

See [API reference](docs/api.md), [architecture](docs/architecture.md), and [evaluation methodology](docs/evaluation.md).

## Project structure

```text
backend/app/
  agent/          bounded Groq tool orchestration and offline fallback
  api/            FastAPI endpoints
  database/       SQLAlchemy models, SQLite setup, and Pydantic schemas
  evaluation/     retrieval metrics
  ingestion/      CSV/JSON sources and normalization
  ranking/        transparent candidate-job scoring
  search/         BM25, FAISS, and hybrid retrieval
  services/       profile, memory, and ingestion operations
frontend/         Streamlit dashboard and styles
data/
  raw/            synthetic CSV demo data
  evaluation/     labeled benchmark and generated reports
scripts/          data generation, ingestion, indexing, evaluation
tests/            unit and integration coverage
```

## Known limitations

- The application uses one local demo identity and does not implement authentication or multi-user access controls.
- Dense semantic search requires the embedding model to be available locally. Hybrid search degrades to BM25 with an explicit warning; semantic-only requests return an error rather than silently mislabeling results.
- Skill extraction uses a small transparent vocabulary; it is not a resume-parsing or skill-inference model.
- Groq improves natural-language understanding but is optional. The no-key assistant supports a deliberately small set of deterministic preference and follow-up patterns.
- The sample benchmark is small and synthetic; it does not establish production ranking quality. LLM tool-selection accuracy is not reported without a labeled tool-call benchmark.
- No live job-board integrations or scraping are included. Implement approved data adapters using the `JobSource` interface and respect the provider's licensing and terms.
