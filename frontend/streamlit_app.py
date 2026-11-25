"""Streamlit UI for the RHEA - Research Hub for Exploration and Analysis.

Features:
  * PDF upload -> page-aware chunking, embedding and indexing into Qdrant + Neo4j
  * Streaming answers (SSE) from the LangGraph conversational agent
  * Visible reasoning steps and numbered citations (source + page + hop distance)
  * Persistent conversation memory per chat thread with auto-compaction indicator
"""

from __future__ import annotations

import json
import os
import uuid

import httpx
import streamlit as st

API_URL = os.getenv("RAG_API_URL", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(
    page_title="RHEA Research Workspace",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.8rem; padding-bottom: 3rem; }
      .stChatMessage { border-radius: 12px; }
      .cit-box { border-left: 3px solid #4C78A8; padding-left: 0.7rem; }
      .small-note { font-size: 0.82rem; color: #6b7280; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
    if "summary" not in st.session_state:
        st.session_state.summary = ""
    if "reader_key" not in st.session_state:
        st.session_state.reader_key = "demo-reader-key"
    if "writer_key" not in st.session_state:
        st.session_state.writer_key = "demo-writer-key"


init_state()


@st.cache_data(ttl=15)
def fetch_health() -> dict | None:
    try:
        response = httpx.get(f"{API_URL}/health", timeout=4)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def source_label(source: dict) -> str:
    meta = source.get("metadata") or {}
    document = meta.get("document") or str(source.get("source", "")).split("#p", 1)[0]
    page = meta.get("page")
    return f"{document} p.{page}" if page else document


def render_citations(sources: list[dict], compact: bool = False) -> None:
    if not sources:
        return
    st.markdown("**Citations**")
    for i, source in enumerate(sources, start=1):
        trust = source.get("trust", "unverified")
        retrieval = source.get("retrieval", "vector")
        hop = source.get("graph_hop_distance")
        badge = "🟢" if trust == "trusted" else ("🔴" if trust == "quarantined" else "🟡")
        path = f" · {hop} hop{'s' if hop != 1 else ''}" if hop else ""
        title = f"[{i}] {badge} {source_label(source)} · {retrieval}{path}"
        if compact:
            st.caption(title)
        else:
            with st.expander(title, expanded=False):
                st.markdown(
                    f"<div class='cit-box'>{source.get('text', '')}</div>",
                    unsafe_allow_html=True,
                )


def post_json(path: str, payload: dict, key: str, timeout: float = 30) -> dict:
    response = httpx.post(
        f"{API_URL}{path}",
        json=payload,
        headers={"X-API-Key": key, "Content-Type": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def clear_thread() -> None:
    try:
        post_json(
            "/v1/chat/clear",
            {"thread_id": st.session_state.thread_id},
            st.session_state.reader_key,
        )
    except Exception:
        pass
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.summary = ""


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Workspace")

    health = fetch_health()
    if health:
        st.success(
            f"API online · {health['provider']}\n\n"
            f"Vector: **{health['vector']['backend']}** · "
            f"Graph: **{health['graph']['backend']}**"
        )
    else:
        st.error(f"API unreachable at {API_URL}. Run `start-all.ps1` first.")

    st.subheader("Retrieval")
    top_k = st.slider("Sources to use (top_k)", 1, 20, 5)

    st.subheader("API keys")
    st.session_state.reader_key = st.text_input(
        "Reader key", value=st.session_state.reader_key, type="password"
    )
    st.session_state.writer_key = st.text_input(
        "Writer key (for PDF upload)", value=st.session_state.writer_key, type="password"
    )

    st.subheader("Conversation memory")
    turns = len(st.session_state.messages) // 2
    st.caption(f"Turns in this chat: {turns}")
    if st.session_state.summary:
        words = len(st.session_state.summary.split())
        with st.expander(f"Auto-summary active ({words} words)"):
            st.write(st.session_state.summary)
    else:
        st.caption("No compaction yet — full history is in the context window.")
    if st.button("🔄 New chat", use_container_width=True):
        clear_thread()
        st.rerun()

    st.divider()
    st.subheader("📄 Ingest PDF")
    uploaded = st.file_uploader(
        "Choose one or more PDFs", type=["pdf"], accept_multiple_files=True
    )
    trust_choice = st.radio("Declared source trust", ["trusted", "unverified"], index=0)
    if st.button("Embed + index PDFs", use_container_width=True, disabled=not uploaded):
        if not health:
            st.error("API is offline; cannot ingest.")
        else:
            for pdf in uploaded or []:
                with st.spinner(f"Reading, chunking and embedding {pdf.name}…"):
                    try:
                        response = httpx.post(
                            f"{API_URL}/v1/ingest/pdf",
                            files={
                                "file": (pdf.name, pdf.getvalue(), "application/pdf")
                            },
                            data={"trust": trust_choice},
                            headers={"X-API-Key": st.session_state.writer_key},
                            timeout=180,
                        )
                        response.raise_for_status()
                        result = response.json()
                        st.success(
                            f"**{pdf.name}** → {result['documents']} pages, "
                            f"{result['chunks']} chunks, {result['entities']} entities, "
                            f"{result['relations']} relations "
                            f"({result['backends']['vector']} + {result['backends']['graph']})"
                        )
                        if result.get("quarantined"):
                            st.warning(f"Quarantined: {', '.join(result['quarantined'])}")
                    except httpx.HTTPStatusError as exc:
                        st.error(
                            f"{pdf.name}: HTTP {exc.response.status_code} - {exc.response.text}"
                        )
                    except Exception as exc:
                        st.error(f"{pdf.name}: {exc}")

    st.caption(
        "Pages are stored as `file.pdf#pN` with page metadata so every answer "
        "can cite the exact page it came from."
    )


# ---------------------------------------------------------------------------
# Main chat
# ---------------------------------------------------------------------------
st.title("RHEA Research Workspace")
st.caption(
    "Ask questions across your PDFs and the bundled corpus. Answers are "
    "streamed, grounded in hybrid vector + knowledge-graph retrieval, and "
    "cited by source and page. Conversation memory is kept per thread."
)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("steps") and message["role"] == "assistant":
            with st.expander("🧠 Agent reasoning", expanded=False):
                for i, step in enumerate(message["steps"], start=1):
                    st.caption(f"{i}. {step}")
        if message.get("sources") and message["role"] == "assistant":
            render_citations(message["sources"], compact=False)

prompt = st.chat_input("Ask a question about your documents…")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        status = st.status("🧠 Agent reasoning…", expanded=False)
        placeholder = st.empty()
        steps: list[str] = []
        sources: list[dict] = []
        final: dict | None = None
        error: str | None = None

        try:
            with httpx.stream(
                "POST",
                f"{API_URL}/v1/chat/stream",
                json={
                    "message": prompt,
                    "thread_id": st.session_state.thread_id,
                    "top_k": top_k,
                },
                headers={"X-API-Key": st.session_state.reader_key},
                timeout=120,
            ) as response:
                response.raise_for_status()
                event_type = ""
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        try:
                            data = json.loads(line.split(":", 1)[1].strip())
                        except json.JSONDecodeError:
                            continue
                        if event_type == "step":
                            steps.append(data.get("content", ""))
                            status.write(f"**{len(steps)}.** {data.get('content', '')}")
                        elif event_type == "sources":
                            sources = data.get("sources", [])
                            status.write(
                                f"📚 Retrieved {len(sources)} source(s) — "
                                + ", ".join(source_label(s) for s in sources[:4])
                            )
                        elif event_type == "token":
                            current = placeholder.markdown  # keep reference
                            buffered = getattr(st.session_state, "_stream_buffer", "") + data.get(
                                "content", ""
                            )
                            st.session_state._stream_buffer = buffered
                            current(buffered + "▌")
                        elif event_type == "summary":
                            st.session_state.summary = data.get("summary", "")
                            st.toast("Context window exceeded — older turns compacted into memory.")
                            status.write("🗜️ Auto-compacted older turns into a memory summary.")
                        elif event_type == "error":
                            error = data.get("content", "Streaming error")
                        elif event_type == "done":
                            final = data
        except Exception as exc:
            error = str(exc)

        answer = (final or {}).get("answer", getattr(st.session_state, "_stream_buffer", ""))
        if error:
            placeholder.error(error)
            answer = f"⚠️ {error}"
        else:
            placeholder.markdown(answer)
        status.update(label="🧠 Agent reasoning ✓", state="complete", expanded=False)
        if hasattr(st.session_state, "_stream_buffer"):
            del st.session_state._stream_buffer

        if final:
            sources = final.get("sources", sources)
            steps = final.get("steps", steps)
            if final.get("summary"):
                st.session_state.summary = final["summary"]
            st.caption(
                f"{final.get('provider')} · {final.get('latency_ms')} ms · "
                f"{len(sources)} cited sources"
                + (" · ⚠️ output flagged" if final.get("output_flagged") else "")
            )

        render_citations(sources)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "steps": steps,
        }
    )
