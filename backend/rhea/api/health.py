"""Public health endpoint."""

from fastapi import APIRouter, Depends

from rhea.api.deps import get_services
from rhea.core.bootstrap import Services

router = APIRouter(tags=["health"])


@router.get("/health")
def health(services: Services = Depends(get_services)) -> dict:
    return {
        "status": "ok",
        "vector": {
            "backend": services.vector_store.backend_name,
            "healthy": services.vector_store.health(),
        },
        "graph": {
            "backend": services.graph_store.backend_name,
            "healthy": services.graph_store.health(),
        },
        "canonical": {
            "backend": services.canonical_store.backend_name,
            "healthy": services.canonical_store.health(),
        },
        "object_store": services.object_store.backend_name,
        "provider": services.agent.llm.name,
    }
