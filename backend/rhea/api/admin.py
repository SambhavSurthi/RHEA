"""Admin endpoints: metrics and approval-gated destructive actions."""

from fastapi import APIRouter, Depends

from rhea.api.deps import get_services
from rhea.auth.rbac import approval_registry, require_approval, require_role
from rhea.core.bootstrap import Services

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.post("/approvals", dependencies=[Depends(require_role("admin"))])
def request_approval(action: str) -> dict:
    """Mint a short-lived, single-use approval token for a named destructive action."""
    token = approval_registry.issue(action)
    return {"action": action, "approval_token": token, "expires_in_seconds": 300}


@router.post(
    "/purge",
    dependencies=[Depends(require_role("admin")), Depends(require_approval("purge"))],
)
def purge_index(services: Services = Depends(get_services)) -> dict:
    """Example destructive action: clears the in-memory fallback stores."""
    if hasattr(services.vector_store, "records"):
        services.vector_store.records.clear()
    if hasattr(services.graph_store, "docs"):
        services.graph_store.docs.clear()
        services.graph_store.doc_entities.clear()
        services.graph_store.relations.clear()
    return {"status": "purged"}
