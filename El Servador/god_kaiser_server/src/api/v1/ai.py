"""
AI/God Layer Integration Endpoints (Phase K4 L3.3 + Phase 5)

- POST /v1/ai/query — Natural language query (rule-based stub; LLM optional later)
- POST /v1/ai/chat  — Agentic debug chat via ClaudeDebugAgent (AUT-270)
- GET  /v1/ai/chat/history — In-memory conversation history
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..deps import ActiveUser, DBSession
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/ai", tags=["ai"])

# ---------------------------------------------------------------------------
# In-memory chat history (session_id → list of message dicts)
# Not persisted across server restarts — intentional for V1.
# ---------------------------------------------------------------------------
_chat_histories: dict[str, list[dict]] = {}


class AIQueryRequest(BaseModel):
    """Natural language query request."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural language question, e.g. 'Wie ist die Temperatur in Zone Bluete-A?'",
    )


class AIQueryResponse(BaseModel):
    """Structured response for NLQ (V1: rule-based placeholder)."""

    answer: str = Field(..., description="Text answer or guidance")
    sources: list[str] = Field(default_factory=list, description="API or data sources used")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score 0–1")


@router.post("/query", response_model=AIQueryResponse)
async def natural_language_query(
    request: AIQueryRequest,
    _user: ActiveUser,
    _db: DBSession,
) -> AIQueryResponse:
    """Natural language query (V1: rule-based stub).

    Examples:
    - 'Wie ist die Temperatur in Zone Bluete-A?' → guidance to use zone KPIs or sensor API
    - 'Welche Sensoren haben hohe Fehlerrate?' → guidance to use export or diagnostics

    V2 can add LLM + context injection for real answers.
    """
    q = request.query.strip().lower()
    if "temperatur" in q or "zone" in q:
        return AIQueryResponse(
            answer="Für Zonen-Temperatur nutzen Sie GET /api/v1/zone/context/{zone_id}/kpis (VPD/Temp) oder die Sensor-API pro Gerät.",
            sources=["/api/v1/zone/context/{zone_id}/kpis", "/api/v1/sensors"],
            confidence=0.8,
        )
    if "fehler" in q or "anomal" in q or "sensor" in q:
        return AIQueryResponse(
            answer="Für Sensor-Status und Anomalien: GET /api/v1/export/components oder Diagnostik-API.",
            sources=["/api/v1/export/components", "/api/v1/diagnostics"],
            confidence=0.7,
        )
    return AIQueryResponse(
        answer="NLQ V1 (regelbasiert). Nennen Sie konkret Temperatur, Zone, Fehler oder Sensoren für gezielte Hinweise. Vollständige Abfragen folgen in V2 (LLM + Kontext).",
        sources=[],
        confidence=0.5,
    )


# ---------------------------------------------------------------------------
# AUT-270: ClaudeDebugAgent Chat Endpoints
# ---------------------------------------------------------------------------


class AIChatRequest(BaseModel):
    """Request body for the agentic debug chat endpoint."""

    message: str = Field(..., min_length=1, description="User message for the debug agent")
    session_id: str = Field(..., min_length=1, description="Conversation session identifier")
    esp_id: Optional[str] = Field(default=None, description="Optional ESP device ID for focused analysis")
    context: Optional[dict] = Field(default=None, description="Optional extra context dict")


@router.post(
    "/chat",
    summary="Agentic debug chat (AUT-270)",
    description=(
        "Run an agentic debug session with ClaudeDebugAgent. "
        "Returns a Server-Sent Events (SSE) stream of the agent's response. "
        "Each SSE line is prefixed with 'data: '."
    ),
)
async def chat(
    request: AIChatRequest,
    db: DBSession,
    _user: ActiveUser,
) -> StreamingResponse:
    """POST /v1/ai/chat — Streaming agentic debug chat."""
    from ...autoops.core.api_client import GodKaiserClient
    from ...core.config import get_settings
    from ...services.claude_debug_agent import ClaudeDebugAgent

    settings = get_settings()
    client = GodKaiserClient(base_url=settings.server.internal_url)
    agent = ClaudeDebugAgent(client=client, db_session=db)

    # Record user message in history
    history = _chat_histories.setdefault(request.session_id, [])
    history.append({"role": "user", "content": request.message})

    async def _stream_and_record() -> "AsyncIterator[str]":
        collected_chunks: list[str] = []
        async for chunk in agent.run(
            user_message=request.message,
            session_id=request.session_id,
            esp_id=request.esp_id,
            context=request.context,
        ):
            collected_chunks.append(chunk)
            yield chunk
        # Persist full assistant response in history
        full_response = "".join(
            c.removeprefix("data: ").removesuffix("\n\n") for c in collected_chunks
        )
        history.append({"role": "assistant", "content": full_response})

    from typing import AsyncIterator

    return StreamingResponse(
        _stream_and_record(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/chat/history",
    summary="Chat history (AUT-270)",
    description="Returns the in-memory conversation history for a session. Not persisted across restarts.",
)
async def get_chat_history(
    session_id: str = Query(..., description="Session identifier"),
    _user: ActiveUser = None,  # type: ignore[assignment]
) -> dict:
    """GET /v1/ai/chat/history?session_id=... — Retrieve conversation history."""
    messages = _chat_histories.get(session_id, [])
    return {"session_id": session_id, "messages": messages}
