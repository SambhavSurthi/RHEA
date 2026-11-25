"""Conversational hybrid RAG built with LangGraph.

Adds three things on top of the single-shot RAGAgent:

* **Memory** -- a LangGraph ``MemorySaver`` checkpointer keeps each thread's
  history and running summary, so follow-up questions have context.
* **Auto-compaction** -- when the history exceeds a rough word budget, older
  turns are summarized and replaced by the summary while the most recent turns
  stay verbatim. This keeps the context window bounded.
* **Streaming / reasoning trace** -- node updates are exposed as ``step`` and
  ``sources`` events and the LLM token stream is forwarded as ``token`` events,
  which the SSE endpoint relays to the Streamlit UI.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph

from rhea.domain.models import ChatResponse, SourceResult
from rhea.pipelines.retrieval import HybridRetriever
from rhea.services.llm import LLMProvider
from rhea.services.security import validate_output


class ChatState(TypedDict, total=False):
    question: str
    top_k: int
    stream_mode: bool
    history: list[dict[str, str]]
    summary: str
    query: str
    sources: list[SourceResult]
    entities: list[str]
    steps: list[str]
    answer: str
    output_flagged: bool
    compacted: bool


class ConversationalRAG:
    """LangGraph state machine: prepare -> retrieve -> generate -> remember."""

    def __init__(
        self,
        retriever: HybridRetriever,
        llm: LLMProvider,
        memory_max_tokens: int = 1800,
        memory_keep_recent: int = 4,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.memory_max_tokens = max(400, memory_max_tokens)
        self.keep_recent = max(2, memory_keep_recent)
        self.checkpointer = MemorySaver()

        graph = StateGraph(ChatState)
        graph.add_node("prepare", self._prepare)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("generate", self._generate)
        graph.add_node("remember", self._remember)
        graph.set_entry_point("prepare")
        graph.add_edge("prepare", "retrieve")
        graph.add_edge("retrieve", "generate")
        graph.add_edge("generate", "remember")
        graph.add_edge("remember", END)
        self.graph = graph.compile(checkpointer=self.checkpointer)

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _dump_sources(sources: list[Any]) -> list[dict[str, Any]]:
        return [s.model_dump() if hasattr(s, "model_dump") else dict(s) for s in sources]

    @staticmethod
    def _emit(payload: dict[str, Any]) -> None:
        """Send a custom event when running under graph.stream(); no-op otherwise."""
        try:
            get_stream_writer()(payload)
        except Exception:
            pass

    def _prepare(self, state: ChatState) -> ChatState:
        history = list(state.get("history", []))
        recent = history[-2:]
        summary = state.get("summary", "")
        query = state["question"]
        if summary:
            query += " " + summary[-600:]
        if recent:
            query += " " + " ".join(m["content"][:200] for m in recent)
        # Reset the visible reasoning trace for each new turn; the checkpointer
        # still keeps history and summary across turns.
        steps = [
            f"Prepared retrieval query with {len(recent)} recent turn(s)"
            + (" and memory summary" if summary else ""),
        ]
        return {"query": query, "steps": steps}

    def _retrieve(self, state: ChatState) -> ChatState:
        result = self.retriever.retrieve(state["query"], state.get("top_k", 5))
        sources = result.sources
        vector_hits = sum(1 for s in sources if s.retrieval in ("vector", "hybrid"))
        graph_hits = sum(1 for s in sources if s.retrieval in ("graph", "hybrid"))
        deepest = max((s.graph_hop_distance or 0 for s in sources), default=0)
        steps = [
            *state.get("steps", []),
            f"Vector search + graph traversal completed ({vector_hits} vector-backed, "
            f"{graph_hits} graph-backed sources)",
            f"RRF fusion + trust reranking kept {len(sources)} sources"
            + (f"; deepest graph path {deepest} hop(s)" if deepest else ""),
        ]
        # Plain dicts keep LangGraph checkpoints portable (no custom classes).
        return {
            "sources": [s.model_dump() for s in sources],
            "entities": result.entities,
            "steps": steps,
        }

    def _generate(self, state: ChatState) -> ChatState:
        question = state["question"]
        sources = state.get("sources", [])
        history = state.get("history", [])
        summary = state.get("summary", "")

        if state.get("stream_mode"):
            parts: list[str] = []
            for token in self.llm.stream_answer(question, sources, history, summary):
                parts.append(token)
                self._emit({"type": "token", "content": token})
            answer = "".join(parts)
        else:
            answer = self.llm.answer(question, sources, history, summary)

        scan = validate_output(answer)
        steps = [
            *state.get("steps", []),
            f"Generated grounded answer from {len(sources)} source(s)"
            + (f" using {self.llm.name} provider" if self.llm.name else ""),
        ]
        return {
            "answer": answer,
            "output_flagged": scan.flagged,
            "steps": steps,
        }

    def _safe_summarize(self, text: str) -> str:
        try:
            return self.llm.summarize(text) or ""
        except Exception:
            # Deterministic fallback if a hosted provider is unavailable.
            sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
            return ". ".join(sentences[:8]) + "." if sentences else ""

    def _remember(self, state: ChatState) -> ChatState:
        history = list(state.get("history", []))
        history.extend(
            [
                {"role": "user", "content": state["question"]},
                {"role": "assistant", "content": state.get("answer", "")},
            ]
        )
        summary = state.get("summary", "")
        steps = list(state.get("steps", []))
        tokens = sum(len(m["content"].split()) for m in history) + len(summary.split())
        compacted = False

        if tokens > self.memory_max_tokens and len(history) > self.keep_recent:
            cutoff = len(history) - self.keep_recent
            older = history[:cutoff]
            kept = history[cutoff:]
            text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in older)
            if summary:
                text = f"PRIOR SUMMARY:\n{summary}\n\n{text}"
            new_summary = self._safe_summarize(text)
            if new_summary:
                summary = new_summary
                history = kept
                compacted = True
                remaining = sum(len(m["content"].split()) for m in history)
                remaining += len(summary.split())
                steps.append(
                    f"Auto-compacted {cutoff} older message(s) into a memory summary "
                    f"(history {tokens} -> {remaining} words)"
                )

        return {
            "history": history,
            "summary": summary,
            "compacted": compacted,
            "steps": steps,
        }

    def invoke(self, message: str, thread_id: str = "default", top_k: int = 5) -> ChatResponse:
        started = time.perf_counter()
        result = self.graph.invoke(
            {"question": message, "top_k": top_k, "stream_mode": False},
            config=self._config(thread_id),
        )
        return ChatResponse(
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
            entities=result.get("entities", []),
            steps=result.get("steps", []),
            summary=result.get("summary", ""),
            output_flagged=result.get("output_flagged", False),
            provider=self.llm.name,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            thread_id=thread_id,
        )

    def stream(
        self, message: str, thread_id: str = "default", top_k: int = 5
    ) -> Iterator[dict[str, Any]]:
        """Yield SSE-ready event dictionaries in execution order."""
        started = time.perf_counter()
        config = self._config(thread_id)
        seen_steps = 0
        for mode, chunk in self.graph.stream(
            {"question": message, "top_k": top_k, "stream_mode": True},
            config=config,
            stream_mode=["updates", "custom"],
        ):
            if mode == "custom":
                yield chunk
                continue
            for _node, update in chunk.items():
                steps = update.get("steps", [])
                if len(steps) > seen_steps:
                    for step in steps[seen_steps:]:
                        yield {"type": "step", "content": step}
                    seen_steps = len(steps)
                if "sources" in update:
                    yield {
                        "type": "sources",
                        "sources": self._dump_sources(update["sources"]),
                        "entities": update.get("entities", []),
                    }
                if update.get("compacted"):
                    yield {"type": "summary", "summary": update.get("summary", "")}

        final = self.graph.get_state(config).values
        yield {
            "type": "done",
            "answer": final.get("answer", ""),
            "sources": self._dump_sources(final.get("sources", [])),
            "entities": final.get("entities", []),
            "steps": final.get("steps", []),
            "summary": final.get("summary", ""),
            "output_flagged": final.get("output_flagged", False),
            "provider": self.llm.name,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "thread_id": thread_id,
        }

    def clear(self, thread_id: str) -> None:
        try:
            self.checkpointer.delete_thread(thread_id)
        except Exception:
            pass
