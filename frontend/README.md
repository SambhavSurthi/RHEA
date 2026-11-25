# Frontend (Streamlit)

`streamlit_app.py` is the only UI entry point. It is intentionally kept thin: it calls the backend API and renders what the backend returns.

## Features

- Multi-PDF upload with declared trust level; ingestion progress and index statistics.
- Streaming chat answers via `POST /v1/chat/stream` (SSE: `step`, `sources`, `token`, `summary`, `done`).
- Expandable reasoning trace and numbered citation chips (document, page, trust, retrieval type, hop distance, snippet).
- Per-thread conversation memory, turn counter, auto-summary indicator and "New chat" reset.

## Configuration

`RAG_API_URL` (default `http://127.0.0.1:8000`) points at the backend. `start-all.ps1` sets it automatically if the API had to move to another port. API keys are entered in the sidebar (reader key for queries, writer key for uploads).

## Run

```powershell
# From the repository root, with the backend running:
$env:PYTHONPATH = 'backend'
streamlit run frontend/streamlit_app.py --server.port 8501
```

Or start everything with `.\start-all.ps1`. The `Dockerfile` in this folder builds a containerized version used by `infra/docker-compose.yml`.
