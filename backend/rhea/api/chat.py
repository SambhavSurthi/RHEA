"""Conversational endpoints: memory, streaming and thread management."""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from rhea.api.deps import get_services
from rhea.auth.rbac import require_role
from rhea.core.bootstrap import Services
from rhea.core.observability import REQUESTS
from rhea.domain.models import ChatRequest, ChatResponse

router = APIRouter(prefix="/v1/chat", tags=["chat"])


def _json_default(obj: object) -> object:
    """Make SSE serialization tolerant of Pydantic models and similar objects."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return str(obj)


@router.post("", response_model=ChatResponse, dependencies=[Depends(require_role("reader"))])
def chat(
    request: ChatRequest, services: Services = Depends(get_services)
) -> ChatResponse:
    """Single-shot conversational query with persistent thread memory."""
    try:
        result = services.chat.invoke(request.message, request.thread_id, request.top_k)
        REQUESTS.labels(endpoint="chat", status="ok").inc()
        return result
    except Exception:
        REQUESTS.labels(endpoint="chat", status="error").inc()
        raise


@router.post("/stream", dependencies=[Depends(require_role("reader"))])
def chat_stream(
    request: ChatRequest, services: Services = Depends(get_services)
) -> StreamingResponse:
    """Server-Sent Events stream of reasoning steps, sources and answer tokens."""

    def generate():
        try:
            for event in services.chat.stream(
                request.message, request.thread_id, request.top_k
            ):
                yield (
                    f"event: {event['type']}\n"
                    f"data: {json.dumps(event, ensure_ascii=False, default=_json_default)}\n\n"
                )
            REQUESTS.labels(endpoint="chat_stream", status="ok").inc()
        except Exception:
            REQUESTS.labels(endpoint="chat_stream", status="error").inc()
            yield (
                "event: error\n"
                'data: {"type":"error","content":"Streaming failed. Check API logs."}\n\n'
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/clear", dependencies=[Depends(require_role("reader"))])
def chat_clear(
    thread_id: str = "default", services: Services = Depends(get_services)
) -> dict:
    """Forget a conversation thread (memory + summary)."""
    services.chat.clear(thread_id)
    return {"status": "cleared", "thread_id": thread_id}
