import json
from pathlib import Path

from rhea.core.bootstrap import build_services
from rhea.domain.models import EvalCase
from rhea.pipelines.evaluation import evaluate
from rhea.pipelines.ingestion import load_sample_documents


def load_cases() -> list[EvalCase]:
    path = Path(__file__).resolve().parents[2] / "data" / "eval.json"
    data = json.loads(path.read_text())
    return [EvalCase(**item) for item in data]


def main() -> None:
    services = build_services()
    services.ingestion.ingest(load_sample_documents())
    summary = evaluate(services.agent, load_cases())
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
