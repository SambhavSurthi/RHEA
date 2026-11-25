"""Document and PDF ingestion endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from rhea.api.deps import get_services
from rhea.auth.rbac import require_role
from rhea.core.bootstrap import Services
from rhea.core.observability import REQUESTS
from rhea.domain.models import IngestRequest, IngestResponse
from rhea.pipelines.ingestion import load_sample_documents
from rhea.pipelines.pdf import documents_from_pdf

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


@router.post(
    "/sample", response_model=IngestResponse, dependencies=[Depends(require_role("writer"))]
)
def ingest_sample(services: Services = Depends(get_services)) -> IngestResponse:
    try:
        result = services.ingestion.ingest(load_sample_documents())
        REQUESTS.labels(endpoint="ingest_sample", status="ok").inc()
        return result
    except Exception:
        REQUESTS.labels(endpoint="ingest_sample", status="error").inc()
        raise


@router.post("", response_model=IngestResponse, dependencies=[Depends(require_role("writer"))])
def ingest(
    request: IngestRequest, services: Services = Depends(get_services)
) -> IngestResponse:
    try:
        result = services.ingestion.ingest(request.documents)
        REQUESTS.labels(endpoint="ingest", status="ok").inc()
        return result
    except Exception:
        REQUESTS.labels(endpoint="ingest", status="error").inc()
        raise


@router.post("/pdf", response_model=IngestResponse, dependencies=[Depends(require_role("writer"))])
async def ingest_pdf(
    file: UploadFile = File(...),  # noqa: B008 - FastAPI dependency idiom
    trust: str = "trusted",
    services: Services = Depends(get_services),
) -> IngestResponse:
    """Upload a PDF: extract text per page, chunk, embed and index into
    Qdrant + Neo4j. Page numbers are carried in metadata for citations."""
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    if trust not in ("trusted", "unverified"):
        raise HTTPException(status_code=400, detail="trust must be trusted or unverified")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        documents = documents_from_pdf(filename, data, trust=trust)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}") from exc
    if not documents:
        raise HTTPException(status_code=400, detail="No extractable text found in the PDF.")
    try:
        result = services.ingestion.ingest(documents)
        REQUESTS.labels(endpoint="ingest_pdf", status="ok").inc()
        return result
    except Exception:
        REQUESTS.labels(endpoint="ingest_pdf", status="error").inc()
        raise
