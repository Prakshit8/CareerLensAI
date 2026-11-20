# CareerLens AI

CareerLens AI is a full-stack, local-first AI job discovery platform that combines keyword search, semantic retrieval, explainable ranking, persistent candidate memory, and an optional Groq-powered career assistant.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?logo=streamlit&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)

> **Portfolio demo:** The included 120 job records are clearly labeled synthetic listings. They are fictional examples for demonstration and evaluation, not real vacancies.

## Key Features

- **Hybrid job search** - BM25 keyword retrieval combined with MiniLM embeddings and FAISS using Reciprocal Rank Fusion.
- **Personalized recommendations** - Transparent weighted scoring across skills, experience, location, employment preferences, salary, and semantic relevance.
- **Persistent memory** - Candidate profile, preferences, conversations, saved jobs, search history, and feedback stored in SQLite.
- **Groq career agent** - Optional tool-calling assistant for search, profile updates, memories, recommendations, saved jobs, and feedback.
- **Resume intake** - PDF text extraction and transparent, reviewable skill detection.
- **Explainable results** - Match scores, retrieved-component details, skill overlap, location evidence, and eligibility status.
- **Offline fallback** - Core search and recommendations continue without a Groq API key.
- **Evaluation pipeline** - Reproducible Precision@K, Recall@K, MRR, nDCG@K, hit rate, p50/p95 latency, and error-rate reports.

## Architecture

```text
Streamlit Dashboard
        |
        v
FastAPI REST API
        |
        +--> SQLite + SQLAlchemy
        +--> BM25 keyword search
        +--> MiniLM + FAISS semantic search
        +--> RRF + weighted ranking
        +--> Optional Groq tool-calling agent
```

See [Architecture](docs/architecture.md) and [API documentation](docs/api.md) for implementation details.

## Evaluation Snapshot

The checked-in benchmark uses four labeled natural-language queries and 120 explicitly synthetic listings.

| Retrieval mode | MRR | Precision@5 | Recall@5 | nDCG@5 | Recall@10 | nDCG@10 | p50 latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| Keyword | 1.000 | 0.850 | 0.425 | 0.888 | 0.900 | 0.908 | 3.176 ms |
| Semantic | 1.000 | 1.000 | 0.500 | 1.000 | 0.875 | 0.918 | 40.066 ms |
| Hybrid | 1.000 | 1.000 | 0.500 | 1.000 | 0.925 | 0.951 | 39.978 ms |
| Personalized | 1.000 | 1.000 | 0.500 | 1.000 | 0.900 | 0.931 | 41.811 ms |

These values are actual benchmark outputs from the included labeled synthetic dataset, not live recruitment data. Evaluation methodology is documented in [Evaluation](docs/evaluation.md).

## Repository Structure

```text
backend/app/
  agent/          Groq orchestration and local fallback
  api/            FastAPI routes
  database/       SQLAlchemy models and schemas
  evaluation/     Metrics and reporting
  ingestion/      CSV/JSON data sources and normalization
  ranking/        Explainable recommendation scoring
  search/         BM25, FAISS, and hybrid retrieval
  services/       Profile, memory, and ingestion services
frontend/
  app.py          Streamlit dashboard
  styles/         Custom CSS
data/
  raw/            Synthetic demo dataset
  evaluation/     Labeled queries and reports
scripts/          Dataset, database, index, and evaluation commands
tests/            Unit and integration tests
docs/             Architecture, API, and evaluation documentation
```

## Quick Start on Windows

### 1. Create and activate an environment

```bat
py -3.10 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure the local environment

```bat
copy .env.example .env
```

For core job search, profile, memory, and recommendations, Groq is optional. Leave `GROQ_API_KEY` empty to use deterministic local assistant search.

```dotenv
DATABASE_URL=sqlite:///data/careerlens.db
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-20b
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
VECTOR_INDEX_DIR=data/indexes
DEMO_IDENTITY=local-demo
RRF_CONSTANT=60
```

Never commit `.env` or expose an API key in frontend code or logs.

### 3. Seed the synthetic job dataset

```bat
python -m scripts.generate_demo_jobs
python -m scripts.seed_database
```

The seed command supports CSV or JSON input:

```bat
python -m scripts.seed_database --input data\raw\jobs.csv --source synthetic-demo
python -m scripts.seed_database --input path\to\jobs.json --source licensed-dataset
```

### 4. Build the semantic index

```bat
python -m scripts.build_index
```

The first build downloads `all-MiniLM-L6-v2`. Subsequent builds reuse and validate the persisted FAISS index.

### 5. Start the application

Open two terminals:

```bat
venv\Scripts\activate
uvicorn backend.app.main:app --reload
```

```bat
venv\Scripts\activate
streamlit run frontend\app.py
```

- Streamlit: <http://localhost:8501>
- FastAPI docs: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

PowerShell users can activate with:

```powershell
.\venv\Scripts\Activate.ps1
```

## Run Tests and Evaluation

```bat
pytest -q
python -m scripts.evaluate_search
```

Evaluation reports are written to `data/evaluation/reports/` as timestamped JSON and CSV files. The latest run is also stored in SQLite.

## Docker

Create `.env`, then run:

```bat
docker compose up --build
```

Docker exposes:

- Streamlit: <http://localhost:8501>
- FastAPI: <http://localhost:8000>

SQLite and FAISS data are mounted under `data/`.

## Example API Requests

Search jobs:

```bat
curl -X POST http://127.0.0.1:8000/api/search -H "Content-Type: application/json" -d "{\"query\":\"entry-level AI internships with Python and RAG\",\"mode\":\"hybrid\",\"limit\":10}"
```

Update the local profile:

```bat
curl -X PATCH http://127.0.0.1:8000/api/profiles/me -H "Content-Type: application/json" -d "{\"skills\":[\"Python\",\"RAG\"],\"experience_level\":\"Fresher\",\"preferred_locations\":[\"Remote\"]}"
```

Ask the career assistant:

```bat
curl -X POST http://127.0.0.1:8000/api/assistant/chat -H "Content-Type: application/json" -d "{\"message\":\"Find remote AI internship opportunities\"}"
```

## Technology Stack

| Area | Technology |
|---|---|
| Backend | Python, FastAPI, Pydantic, SQLAlchemy |
| Database | SQLite |
| Search | BM25, Sentence Transformers, FAISS |
| Ranking | Configurable weighted score with RRF |
| AI assistant | Groq function calling, local fallback |
| Frontend | Streamlit, custom CSS |
| PDF intake | pypdf |
| Testing | Pytest, FastAPI TestClient |
| Deployment | Docker, Docker Compose |

## Current Limitations

- Uses a single local demo identity; authentication and multi-user isolation are not implemented.
- Resume skill extraction uses a transparent vocabulary rather than a trained resume model.
- Dense semantic search requires an available local Hugging Face model and FAISS.
- Groq is optional and can be unavailable; the application reports degraded or local-fallback behavior instead of inventing results.
- The labeled benchmark is intentionally small and synthetic.
- No live job-board integration or scraping is included.
- Agent tool-selection and task-completion metrics require separate labeled agent scenarios before meaningful values can be reported.

## License

This repository is provided as a portfolio and educational project. Add a license before publishing it for broader reuse.
