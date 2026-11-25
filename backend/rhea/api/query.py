"""Single-shot hybrid query endpoint."""

from fastapi import APIRouter, Depends

from rhea.api.deps import get_services
from rhea.auth.rbac import require_role
from rhea.core.bootstrap import Services
from rhea.core.observability import REQUESTS
from rhea.domain.models import QueryRequest, QueryResponse

router = APIRouter(prefix="/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(require_role("reader"))])
def query(
    request: QueryRequest, services: Services = Depends(get_services)
) -> QueryResponse:
    try:
        result = services.agent.invoke(request.question, request.top_k)
        REQUESTS.labels(endpoint="query", status="ok").inc()
        return result
    except Exception:
        REQUESTS.labels(endpoint="query", status="error").inc()
        raise
