"""FastAPI application factory and router assembly."""

from fastapi import Depends, FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from rhea.api import admin, chat, evaluation, health, ingest, query
from rhea.auth.rbac import require_role
from rhea.core.bootstrap import build_services
from rhea.core.observability import configure_tracing


def create_app() -> FastAPI:
    """Build the application, its services and all API routers."""
    application = FastAPI(
        title="RHEA - Research Hub for Exploration and Analysis",
        version="0.2.0",
        description=(
            "RHEA: AI research paper assistant - hybrid vector and knowledge-graph "
            "retrieval with cited, streaming answers."
        ),
    )
    services = build_services()
    application.state.services = services
    configure_tracing(
        application, services.settings.otel_enabled, services.settings.otel_service_name
    )

    application.include_router(health.router)
    application.include_router(ingest.router)
    application.include_router(query.router)
    application.include_router(chat.router)
    application.include_router(evaluation.router)
    application.include_router(admin.router)

    @application.get("/metrics", dependencies=[Depends(require_role("admin"))])
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return application


app = create_app()
