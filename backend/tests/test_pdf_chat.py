"""Tests for PDF page-aware ingestion and the conversational LangGraph agent.

These run entirely in memory â€” no Qdrant, Neo4j or hosted LLM required.
"""

from rhea.domain.models import DocumentIn
from rhea.pipelines.ingestion import IngestionService
from rhea.pipelines.pdf import PdfPage, citation_label, documents_from_pdf
from rhea.pipelines.retrieval import HybridRetriever
from rhea.services.chat import ConversationalRAG
from rhea.services.embeddings import HashingEmbedder
from rhea.services.llm import LocalExtractiveProvider
from rhea.stores.graph import InMemoryGraphStore
from rhea.stores.vector import InMemoryVectorStore


def test_pdf_pages_become_page_scoped_documents(monkeypatch):
    monkeypatch.setattr(
        "rhea.pipelines.pdf.extract_pages",
        lambda _data: [
            PdfPage(page=1, text="The Checkout Service depends on Redis."),
            PdfPage(page=3, text="The Checkout Service is monitored by Datadog."),
        ],
    )
    docs = documents_from_pdf("manual.pdf", b"not-a-real-pdf")
    assert [d.source for d in docs] == ["manual.pdf#p1", "manual.pdf#p3"]
    assert docs[1].metadata["page"] == "3"
    assert docs[1].metadata["document"] == "manual.pdf"
    assert citation_label(docs[0].source, docs[0].metadata) == "manual.pdf p.1"


def build_chat(max_tokens: int = 1800) -> ConversationalRAG:
    embedder = HashingEmbedder(64)
    vector = InMemoryVectorStore()
    graph = InMemoryGraphStore()
    IngestionService(embedder, vector, graph).ingest(
        [
            DocumentIn(
                source="manual.pdf#p1",
                text=(
                    "The Checkout Service depends on Redis. "
                    "The Checkout Service is monitored by Datadog."
                ),
                metadata={"document": "manual.pdf", "page": "1"},
                trust="trusted",
            )
        ]
    )
    retriever = HybridRetriever(embedder, vector, graph, vector_k=4, graph_k=4)
    return ConversationalRAG(
        retriever,
        LocalExtractiveProvider(),
        memory_max_tokens=max_tokens,
        memory_keep_recent=2,
    )


def test_chat_returns_cited_sources_and_keeps_memory():
    chat = build_chat()
    first = chat.invoke("What does the Checkout Service depend on?", "thread-1")
    assert first.answer
    assert "[1]" in first.answer
    assert any("manual.pdf" in s.source for s in first.sources)

    second = chat.invoke("What monitors it?", "thread-1")
    state = chat.graph.get_state(chat._config("thread-1")).values
    assert len(state["history"]) == 4  # two user + two assistant messages
    assert "[1]" in second.answer


def test_context_overflow_is_auto_summarized():
    chat = build_chat()
    chat.memory_max_tokens = 30  # force compaction with short synthetic turns
    for _ in range(3):
        chat.invoke("Who owns the Checkout Service and how is it monitored?", "thread-2")
    state = chat.graph.get_state(chat._config("thread-2")).values
    assert state["summary"]
    assert len(state["history"]) <= 2

    chat.clear("thread-2")
    cleared = chat.graph.get_state(chat._config("thread-2")).values
    assert not cleared.get("history")
