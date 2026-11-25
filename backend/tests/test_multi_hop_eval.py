from rhea.domain.models import DocumentIn, EvalCase
from rhea.pipelines.ingestion import IngestionService
from rhea.pipelines.retrieval import HybridRetriever
from rhea.services.agent import RAGAgent
from rhea.services.embeddings import HashingEmbedder
from rhea.services.llm import LocalExtractiveProvider
from rhea.stores.graph import InMemoryGraphStore
from rhea.stores.vector import InMemoryVectorStore


def build_multi_hop_agent():
    embedder = HashingEmbedder(128)
    vector = InMemoryVectorStore()
    graph = InMemoryGraphStore()
    ingestion = IngestionService(embedder, vector, graph)
    retriever = HybridRetriever(embedder, vector, graph, vector_k=4, graph_k=4, graph_max_hops=3)
    agent = RAGAgent(retriever, LocalExtractiveProvider())
    ingestion.ingest(
        [
            DocumentIn(
                source="chain.md",
                text=(
                    "The Embedding Cache depends on the Redis Cluster. "
                    "The Redis Cluster runs on the Cloud Provider. "
                    "The Cloud Provider is monitored by Datadog."
                ),
                trust="trusted",
            )
        ]
    )
    return agent


def test_multi_hop_eval_metric_credits_genuine_traversal():
    from rhea.pipelines.evaluation import evaluate

    agent = build_multi_hop_agent()
    cases = [
        EvalCase(
            question="Which tool monitors the infrastructure that powers the Embedding Cache?",
            expected_sources=["chain.md"],
            expected_keywords=["Datadog"],
            requires_hops=3,
        )
    ]
    summary = evaluate(agent, cases)
    assert summary.multi_hop_cases == 1
    assert summary.multi_hop_hit_rate == 100.0


def test_multi_hop_metric_zero_when_no_multi_hop_cases():
    from rhea.pipelines.evaluation import evaluate

    agent = build_multi_hop_agent()
    cases = [
        EvalCase(
            question="What does the Embedding Cache depend on?",
            expected_sources=["chain.md"],
            expected_keywords=["Redis Cluster"],
        )
    ]
    summary = evaluate(agent, cases)
    assert summary.multi_hop_cases == 0
    assert summary.multi_hop_hit_rate == 0.0
