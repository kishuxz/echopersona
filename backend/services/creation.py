"""Creation state machine — PERSONA_SPEC.md §3.

Session state is stored in Redis as JSON (TTL = SESSION_TTL_SECONDS).

Per-answer flow:
  1. [a/v only] STT via Stage 0 Whisper (full media files, not PCM chunks).
  2. Stage 0 write: insert memory_sources row synchronously — no LLM, no wait.
  3. Deterministic action §4.4  ←  step 3 will plug the evaluator in here.
  4. State transition (pure, tested).
  5. Return NextStep to the router.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from services.question_bank import QuestionEntry, get_steering_bank, questions_in_creation_order

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 7 * 24 * 3600
_SESSION_KEY_PREFIX = "creation_session:"
SHORT_ANSWER_THRESHOLD = 120  # §4.4 — tune against real sessions


# ── Session state ─────────────────────────────────────────────────────────────


class CreationSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    persona_id: str
    user_id: str

    # Traversal
    completed_question_ids: list[str] = Field(default_factory=list)
    current_question_id: str | None = None
    current_probe_id: str | None = None
    followups_used_this_question: int = 0

    # Signal + topic saturation — updated by evaluator (step 3)
    signal_coverage: dict[str, Literal["none", "partial", "saturated"]] = Field(
        default_factory=dict
    )
    topics_well_covered: list[str] = Field(default_factory=list)

    # Stage 0 source IDs pending batch ingestion at session end
    pending_source_ids: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NextStep(BaseModel):
    action: Literal["ask_probe", "steer", "advance", "done"]
    # Text to present to the subject (probe prompt, filled steer text, or None)
    prompt: str | None = None
    # What comes next
    question_id: str | None = None
    probe_id: str | None = None
    question_prompt: str | None = None  # full question text when action=advance
    session: CreationSession


# ── Redis session store ───────────────────────────────────────────────────────

_redis = None


async def _get_redis():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        from config import settings
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def load_session(session_id: str) -> CreationSession | None:
    r = await _get_redis()
    raw = await r.get(f"{_SESSION_KEY_PREFIX}{session_id}")
    if raw is None:
        return None
    return CreationSession.model_validate_json(raw)


async def save_session(session: CreationSession) -> None:
    session = session.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    r = await _get_redis()
    await r.set(
        f"{_SESSION_KEY_PREFIX}{session.session_id}",
        session.model_dump_json(),
        ex=SESSION_TTL_SECONDS,
    )


# ── Pure state-machine logic (no I/O — fully testable) ───────────────────────


def select_next_question(session: CreationSession) -> QuestionEntry | None:
    """Return the next unanswered question in §5.1 creation order.

    Required questions are interspersed in creation order and are never
    skipped by the evaluator — so walking in creation order is sufficient.
    """
    for q in questions_in_creation_order():
        if q.id not in session.completed_question_ids:
            return q
    return None


def deterministic_next_action(
    followups_used: int,
    max_followups: int,
    answer_text: str,
    question: QuestionEntry,
) -> dict:
    """§4.4 deterministic fallback — zero Groq calls.

    Step 3 inserts the real evaluator call before this function; until then
    this is the only decision logic.

    Returns dict: {next_action, probe_id?}
    """
    probes = question.probes
    if followups_used >= max_followups or not probes:
        return {"next_action": "advance"}
    if followups_used == 0 and len(answer_text.strip()) < SHORT_ANSWER_THRESHOLD:
        return {"next_action": "ask_probe", "probe_id": probes[0].id}
    return {"next_action": "advance"}


def apply_action(
    session: CreationSession,
    question: QuestionEntry,
    action: dict,
) -> tuple[CreationSession, NextStep]:
    """Transition session state given an action dict. Pure — no I/O.

    Caller must await save_session(new_session) to persist.
    """
    session = session.model_copy(deep=True)
    next_action = action["next_action"]

    if next_action == "ask_probe":
        probe_id: str = action["probe_id"]
        probe = question.probe_by_id(probe_id)
        session.current_probe_id = probe_id
        session.followups_used_this_question += 1
        return session, NextStep(
            action="ask_probe",
            prompt=probe.prompt if probe else None,
            question_id=session.current_question_id,
            probe_id=probe_id,
            session=session,
        )

    if next_action == "steer":
        steer_id: str = action.get("steer_id", "wrap_up")
        template = get_steering_bank().get(steer_id, "")
        steer_text = template.replace("{topic}", question.category)
        session.current_probe_id = None
        return session, NextStep(
            action="steer",
            prompt=steer_text,
            question_id=session.current_question_id,
            session=session,
        )

    # advance (or done)
    if session.current_question_id:
        session.completed_question_ids.append(session.current_question_id)
    session.current_probe_id = None
    session.followups_used_this_question = 0

    next_q = select_next_question(session)
    if next_q is None:
        session.current_question_id = None
        return session, NextStep(action="done", session=session)

    session.current_question_id = next_q.id
    return session, NextStep(
        action="advance",
        question_id=next_q.id,
        question_prompt=next_q.prompt,
        session=session,
    )


# ── Stage 0 source write ──────────────────────────────────────────────────────


async def _write_stage0(
    session: CreationSession,
    question: QuestionEntry,
    answer_text: str,
    file_id: str = "",
    media_ref: str = "",
) -> str:
    """Write one memory_sources row. Returns source_id."""
    # When answering a probe, record the probe's prompt as question_text
    if session.current_probe_id:
        probe = question.probe_by_id(session.current_probe_id)
        question_text = probe.prompt if probe else question.prompt
    else:
        question_text = question.prompt

    captured_at = datetime.now(timezone.utc).isoformat()

    from services.ingestion.source_store import create_source_record  # noqa: PLC0415
    return await create_source_record(
        user_id=session.user_id,
        persona_id=session.persona_id,
        modality=question.modality,
        question_category=question.category,
        question_text=question_text,
        group_name="",
        file_id=file_id,
        text_content=answer_text,
        source_question_id=question.id,
        source_type="answer",
        media_ref=media_ref,
        captured_at=captured_at,
    )


# ── High-level capture handlers ───────────────────────────────────────────────


async def capture_text(
    session: CreationSession,
    answer_text: str,
) -> tuple[CreationSession, NextStep, str]:
    """Process a typed answer. Returns (updated_session, next_step, source_id)."""
    bank = {q.id: q for q in questions_in_creation_order()}
    question = bank.get(session.current_question_id or "")
    if question is None:
        raise ValueError(f"No active question in session {session.session_id}")

    source_id = await _write_stage0(session, question, answer_text)
    session = session.model_copy(
        update={"pending_source_ids": session.pending_source_ids + [source_id]}
    )

    action = deterministic_next_action(
        session.followups_used_this_question,
        question.max_followups,
        answer_text,
        question,
    )
    session, next_step = apply_action(session, question, action)
    await save_session(session)
    return session, next_step, source_id


async def capture_av(
    session: CreationSession,
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> tuple[CreationSession, NextStep, str, str]:
    """Process an audio/video answer: upload → STT → Stage 0 → action.

    Returns (updated_session, next_step, source_id, answer_text).
    """
    bank = {q.id: q for q in questions_in_creation_order()}
    question = bank.get(session.current_question_id or "")
    if question is None:
        raise ValueError(f"No active question in session {session.session_id}")

    from services.ingestion.source_store import SOURCE_BUCKET, upload_source_file  # noqa: PLC0415
    from services.ingestion.stage0 import transcribe_media  # noqa: PLC0415

    # Upload first so media_ref is preserved even if STT later fails
    file_id = await upload_source_file(
        user_id=session.user_id,
        file_bytes=file_bytes,
        content_type=content_type,
        filename=filename,
    )
    media_ref = f"storage://{SOURCE_BUCKET}/{file_id}"

    answer_text, _duration = await transcribe_media(file_bytes, filename, content_type)

    source_id = await _write_stage0(
        session, question, answer_text, file_id=file_id, media_ref=media_ref
    )
    session = session.model_copy(
        update={"pending_source_ids": session.pending_source_ids + [source_id]}
    )

    action = deterministic_next_action(
        session.followups_used_this_question,
        question.max_followups,
        answer_text,
        question,
    )
    session, next_step = apply_action(session, question, action)
    await save_session(session)
    return session, next_step, source_id, answer_text


# ── Session lifecycle ─────────────────────────────────────────────────────────


async def start_session(persona_id: str, user_id: str) -> tuple[CreationSession, NextStep]:
    """Create session, select first question, persist."""
    session = CreationSession(persona_id=persona_id, user_id=user_id)
    next_q = select_next_question(session)
    if next_q is None:
        session.current_question_id = None
        next_step = NextStep(action="done", session=session)
    else:
        session.current_question_id = next_q.id
        next_step = NextStep(
            action="advance",
            question_id=next_q.id,
            question_prompt=next_q.prompt,
            session=session,
        )
    await save_session(session)
    return session, next_step


async def finish_session(session: CreationSession, arq_pool) -> list[str]:
    """Enqueue all pending source IDs for batch ingestion (Stages 1-4)."""
    enqueued: list[str] = []
    for source_id in session.pending_source_ids:
        try:
            await arq_pool.enqueue_job("ingest_memory_unit", source_id, session.user_id)
            enqueued.append(source_id)
            logger.info("[creation] enqueued source_id=%s", source_id)
        except Exception as exc:
            logger.error("[creation] failed to enqueue source_id=%s: %s", source_id, exc)
    session = session.model_copy(update={"pending_source_ids": []})
    await save_session(session)
    return enqueued
