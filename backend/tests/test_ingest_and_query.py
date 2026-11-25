from rhea.domain.models import DocumentIn
from rhea.pipelines.ingestion import IngestionService
from rhea.pipelines.retrieval import HybridRetriever
from rhea.services.agent import RAGAgent
from rhea.services.embeddings import HashingEmbedder
from rhea.services.llm import LocalExtractiveProvider
from rhea.stores.graph import InMemoryGraphStore
from rhea.stores.vector import InMemoryVectorStore


def build_local_agent():
    embedder = HashingEmbedder(128)
    vector = InMemoryVectorStore()
    graph = InMemoryGraphStore()
    ingestion = IngestionService(embedder, vector, graph)
    retriever = HybridRetriever(embedder, vector, graph, vector_k=4, graph_k=4)
    agent = RAGAgent(retriever, LocalExtractiveProvider())
    return ingestion, agent


def test_end_to_end_local_pipeline():
    ingestion, agent = build_local_agent()
    ingestion.ingest([
        DocumentIn(
            source="demo.md",
            text=(
                "The Inference Gateway depends on GPU Cluster. "
                "The Inference Gateway is monitored by Prometheus."
            ),
        )
    ])
    result = agent.invoke("How is the Inference Gateway monitored?", top_k=3)
    assert result.sources
    assert any(s.source == "demo.md" for s in result.sources)
    assert "Inference Gateway" in result.answer
