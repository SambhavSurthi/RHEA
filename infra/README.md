# Infrastructure

`docker-compose.yml` defines the runtime topology:

| Service | Image / build | Ports | Notes |
|---|---|---|---|
| `neo4j` | `neo4j:5.26.29-community` | 7474, 7687 | Healthcheck on 7474; data in `neo4j_data` |
| `qdrant` | `qdrant/qdrant:v1.15.4` | 6333, 6334 | Data in `qdrant_data` |
| `api` | `backend/Dockerfile` | 8000 | Gets `.env` plus container-safe DB URLs |
| `frontend` | `frontend/Dockerfile` | 8501 | Gets `RAG_API_URL=http://api:8000` |

Run the full containerized stack:

```powershell
docker compose -f infra/docker-compose.yml up --build
docker compose -f infra/docker-compose.yml down      # volumes are preserved
```

`start-all.ps1` only starts `neo4j` and `qdrant` here, then runs the API and Streamlit locally from `.venv` — this gives the fastest development loop while still using the real databases.
