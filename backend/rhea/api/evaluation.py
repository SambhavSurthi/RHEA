"""Evaluation endpoint."""

from fastapi import APIRouter, Depends

from rhea.api.deps import get_services
from rhea.auth.rbac import require_role
from rhea.core.bootstrap import Services
from rhea.domain.models import EvalSummary, EvaluateRequest
from rhea.pipelines.evaluation import evaluate
from rhea.pipelines.runner import load_cases

router = APIRouter(prefix="/v1", tags=["evaluation"])


@router.post(
    "/evaluate", response_model=EvalSummary, dependencies=[Depends(require_role("admin"))]
)
def run_evaluation(
    request: EvaluateRequest, services: Services = Depends(get_services)
) -> EvalSummary:
    cases = request.cases or load_cases()
    return evaluate(services.agent, cases)
