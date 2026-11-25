from dataclasses import dataclass

from rhea.core.config import Settings, get_settings
from rhea.pipelines.ingestion import IngestionService
from rhea.pipelines.retrieval import HybridRetriever
from rhea.services.agent import RAGAgent
from rhea.services.chat import ConversationalRAG
from rhea.services.embeddings import HashingEmbedder
from rhea.services.llm import (
    AnthropicProvider,
    LLMProvider,
    LocalExtractiveProvider,
    OpenAIProvider,
)
from rhea.services.object_store import ObjectStore, build_object_store
from rhea.stores.graph import GraphStore, InMemoryGraphStore, Neo4jGraphStore
from rhea.stores.relational import CanonicalStore, InMemoryCanonicalStore, PostgresCanonicalStore
from rhea.stores.vector import InMemoryVectorStore, QdrantVectorStore, VectorStore


@dataclass(slots=True)
class Services:
    settings: Settings
    vector_store: VectorStore
    graph_store: GraphStore
    ingestion: IngestionService
    agent: RAGAgent
    chat: ConversationalRAG
    canonical_store: CanonicalStore
    object_store: ObjectStore


def _vector_store(settings: Settings, embedder: HashingEmbedder) -> VectorStore:
    try:
        return QdrantVectorStore(
            settings.qdrant_url,
            settings.qdrant_collection,
            embedder.dimension,
            settings.qdrant_api_key,
        )
    except Exception:
        if not settings.allow_in_memory_fallback:
            raise
        return InMemoryVectorStore()


def _graph_store(settings: Settings) -> GraphStore:
    try:
        return Neo4jGraphStore(
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password,
            settings.neo4j_database,
        )
    except Exception:
        if not settings.allow_in_memory_fallback:
            raise
        return InMemoryGraphStore()


def _canonical_store(settings: Settings) -> CanonicalStore:
    if not settings.postgres_dsn:
        if not settings.allow_in_memory_fallback:
            raise RuntimeError("RHEA_POSTGRES_DSN is required when fallback is disabled")
        return InMemoryCanonicalStore()
    try:
        return PostgresCanonicalStore(
            settings.postgres_dsn,
            settings.postgres_pool_size,
            settings.postgres_statement_timeout,
        )
    except Exception:
        if not settings.allow_in_memory_fallback:
            raise
        return InMemoryCanonicalStore()


def _llm(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "openai" and settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    if provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    return LocalExtractiveProvider()


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or get_settings()
    embedder = HashingEmbedder(settings.embedding_dim)
    vector = _vector_store(settings, embedder)
    graph = _graph_store(settings)
    canonical = _canonical_store(settings)
    objects = build_object_store(settings.object_store_backend, settings.object_store_path)
    ingestion = IngestionService(
        embedder,
        vector,
        graph,
        settings.block_quarantined_ingest,
        canonical_store=canonical,
        object_store=objects,
    )
    retriever = HybridRetriever(
        embedder,
        vector,
        graph,
        settings.top_k_vector,
        settings.top_k_graph,
        settings.rrf_k,
        settings.exclude_quarantined_from_context,
        settings.graph_max_hops,
    )
    llm = _llm(settings)
    agent = RAGAgent(retriever, llm)
    chat = ConversationalRAG(
        retriever,
        llm,
        settings.memory_max_tokens,
        settings.memory_keep_recent,
    )
    return Services(settings, vector, graph, ingestion, agent, chat, canonical, objects)
