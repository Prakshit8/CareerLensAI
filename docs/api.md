# API overview

Start the backend with `uvicorn backend.app.main:app --reload`; OpenAPI is available at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Database-backed health check |
| GET, POST | `/api/jobs` | List/search or manually upsert a listing |
| GET | `/api/jobs/{job_id}` | Retrieve a listing |
| GET | `/api/jobs/{job_id}/similar` | Retrieve similar listings |
| PATCH | `/api/profiles/me` | Read/update the local candidate profile |
| POST | `/api/profiles/me/resume` | Extract selectable text and known skills from PDF |
| POST | `/api/search` | Keyword, semantic, or hybrid search |
| GET | `/api/recommendations` | Personalized recommendations |
| GET | `/api/search/history` | Persistent search history |
| GET, PUT, DELETE | `/api/memories` | Inspect, upsert, or delete persistent memories |
| GET, PUT, DELETE | `/api/saved` | List/save/remove jobs |
| POST | `/api/feedback` | Record like/dislike/not-relevant/applied feedback |
| POST | `/api/assistant/chat` | Persistent conversation with optional tool-calling LLM |
| GET | `/api/assistant/conversations` | List persisted conversations |
| GET | `/api/assistant/conversations/{id}/messages` | Read a conversation |
| GET | `/api/evaluation/runs` | Read stored offline evaluation reports |

Search requests accept `query`, `mode`, `location`, `role`, `experience_level`, `employment_type`, and `limit`. Uploads are restricted to PDF and 5 MB.
