"""Creation flow HTTP endpoints — PERSONA_SPEC.md §3."""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from middleware.auth import get_current_user
from services import persona_store
from services.creation import (
    CreationSession,
    NextStep,
    capture_av,
    capture_text,
    finish_session,
    load_session,
    start_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/creation", tags=["creation"])


# ── Request / response models ─────────────────────────────────────────────────


class StartSessionRequest(BaseModel):
    persona_id: str


class StartSessionResponse(BaseModel):
    session: CreationSession
    next_step: NextStep


class CaptureTextRequest(BaseModel):
    answer_text: str


class CaptureResponse(BaseModel):
    source_id: str
    answer_text: str
    next_step: NextStep


class FinishResponse(BaseModel):
    enqueued_source_ids: list[str]
    total: int


# ── Auth + session helpers ────────────────────────────────────────────────────


async def _require_session(session_id: str, user_id: str) -> CreationSession:
    session = await load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return session


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/session", response_model=StartSessionResponse)
async def create_session(
    payload: StartSessionRequest,
    user_id: str = Depends(get_current_user),
) -> StartSessionResponse:
    """Start a new creation session for a persona."""
    persona = await persona_store.get_persona(payload.persona_id, user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    session, next_step = await start_session(payload.persona_id, user_id)
    return StartSessionResponse(session=session, next_step=next_step)


@router.get("/session/{session_id}", response_model=CreationSession)
async def get_session(
    session_id: str,
    user_id: str = Depends(get_current_user),
) -> CreationSession:
    """Return the current session state."""
    return await _require_session(session_id, user_id)


@router.post("/session/{session_id}/capture/text", response_model=CaptureResponse)
async def capture_text_answer(
    session_id: str,
    payload: CaptureTextRequest,
    user_id: str = Depends(get_current_user),
) -> CaptureResponse:
    """Submit a typed answer; returns Stage 0 source_id + next step."""
    session = await _require_session(session_id, user_id)
    if session.current_question_id is None:
        raise HTTPException(status_code=400, detail="Session is already complete")
    if not payload.answer_text.strip():
        raise HTTPException(status_code=422, detail="answer_text must not be empty")
    session, next_step, source_id = await capture_text(session, payload.answer_text)
    return CaptureResponse(
        source_id=source_id,
        answer_text=payload.answer_text,
        next_step=next_step,
    )


@router.post("/session/{session_id}/capture/av", response_model=CaptureResponse)
async def capture_av_answer(
    session_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
) -> CaptureResponse:
    """Upload audio/video; transcribes via Groq Whisper, then same path as text."""
    session = await _require_session(session_id, user_id)
    if session.current_question_id is None:
        raise HTTPException(status_code=400, detail="Session is already complete")
    content_type = file.content_type or "application/octet-stream"
    if not content_type.startswith(("audio/", "video/")):
        raise HTTPException(status_code=400, detail="File must be audio or video")
    file_bytes = await file.read()
    session, next_step, source_id, answer_text = await capture_av(
        session, file_bytes, file.filename or "upload", content_type
    )
    return CaptureResponse(
        source_id=source_id,
        answer_text=answer_text,
        next_step=next_step,
    )


@router.post("/session/{session_id}/finish", response_model=FinishResponse)
async def finish(
    session_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> FinishResponse:
    """Enqueue all pending source records for batch ingestion (Stages 1-4)."""
    session = await _require_session(session_id, user_id)
    enqueued = await finish_session(session, request.app.state.arq_pool)
    return FinishResponse(enqueued_source_ids=enqueued, total=len(enqueued))
