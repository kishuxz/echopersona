"""Creation state machine — PERSONA_SPEC.md §3.

Session state is stored in Redis as JSON (TTL = SESSION_TTL_SECONDS).

Per-answer flow:
  1. [a/v only] STT via Stage 0 Whisper (full media files, not PCM chunks).
  2. Stage 0 write: insert memory_sources row synchronously — no LLM, no wait.
  3. Evaluator (§4): bounded Groq call → evaluate_next_action(); falls back to §4.4.
  4. State transition (pure, tested).
  5. Return NextStep to the router.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from services.groq_limiter import groq_acquire
from services.question_bank import QuestionEntry, get_steering_bank, questions_in_creation_order

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 7 * 24 * 3600
_SESSION_KEY_PREFIX = "creation_session:"
SHORT_ANSWER_THRESHOLD = 120  # §4.4 — tune against real sessions

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_EVALUATOR_MODEL = "llama-3.1-8b-instant"

_VALID_NEXT_ACTIONS = {"ask_probe", "advance", "steer"}
_VALID_STEER_IDS = {"refocus", "wrap_up", "too_short", "sensitive_ok"}
_VALID_SKIP_REASONS = {"saturated", "capped", "covered_elsewhere", "low_value", None}


def _load_evaluator_prompt() -> str:
    path = Path(__file__).parent.parent / "prompts" / "EVALUATOR_SYSTEM.md"
    text = path.read_text(encoding="utf-8")
    marker_start = "## SYSTEM PROMPT (copy below this line)\n"
    marker_end = "\n## (end of system prompt)"
    start = text.index(marker_start) + len(marker_start)
    end = text.index(marker_end)
    return text[start:end].strip()


_EVALUATOR_SYSTEM_PROMPT = _load_evaluator_prompt()


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

    # Signal + topic saturation — updated by evaluator (§4)
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


# ── Evaluator (§4) ───────────────────────────────────────────────────────────


def _build_evaluator_input(
    question: QuestionEntry,
    answer_text: str,
    session: CreationSession,
) -> dict:
    """Build the §4.1 evaluator user-message JSON. Pure."""
    signal_coverage = {
        k: v for k, v in session.signal_coverage.items()
        if v in ("partial", "saturated")
    }
    return {
        "question": {
            "id": question.id,
            "prompt": question.prompt,
            "category": question.category,
            "intent": question.intent,
            "signals": question.signals,
        },
        "prepared_probes": [
            {"id": p.id, "prompt": p.prompt, "good_when": p.good_when}
            for p in question.probes
        ],
        "answer_text": answer_text,
        "session_state": {
            "followups_used_this_question": session.followups_used_this_question,
            "max_followups": question.max_followups,
            "signal_coverage": signal_coverage,
            "topics_well_covered": session.topics_well_covered,
        },
    }


def _validate_evaluator_output(
    raw: dict,
    question: QuestionEntry,
    session: CreationSession,
) -> dict | None:
    """Apply §4.2 schema check and §4.3 guardrails. Returns safe action dict or None → fallback."""
    try:
        next_action = raw.get("next_action")
        if next_action not in _VALID_NEXT_ACTIONS:
            return None

        # §4.3: enforce max_followups in code regardless of model output
        if next_action == "ask_probe" and session.followups_used_this_question >= question.max_followups:
            return {"next_action": "advance", "skip_reason": "capped"}

        if next_action == "ask_probe":
            probe_id = raw.get("probe_id")
            valid_probe_ids = {p.id for p in question.probes}
            if not probe_id or probe_id not in valid_probe_ids:
                return None  # probe injection blocked → caller falls back

            # §4.3: code override when all target signals are already saturated
            if question.signals and all(
                session.signal_coverage.get(s) == "saturated" for s in question.signals
            ):
                return {"next_action": "advance", "skip_reason": "saturated"}

            # §4.3: conservative default — low-confidence probe request → advance
            confidence = float(raw.get("confidence", 1.0))
            if confidence < 0.5:
                return {"next_action": "advance", "skip_reason": "low_value"}

            return {"next_action": "ask_probe", "probe_id": probe_id}

        if next_action == "steer":
            steer_id = raw.get("steer_id")
            if steer_id not in _VALID_STEER_IDS:
                return None
            return {"next_action": "steer", "steer_id": steer_id}

        # advance
        skip_reason = raw.get("skip_reason")
        if skip_reason == "null":  # model may return the string "null"
            skip_reason = None
        if skip_reason not in _VALID_SKIP_REASONS:
            skip_reason = None
        return {"next_action": "advance", "skip_reason": skip_reason}

    except (TypeError, KeyError, ValueError):
        return None


def _update_coverage(
    session: CreationSession,
    signals_present: list[str],
    topics_touched: list[str],
) -> CreationSession:
    """Accumulate signal_coverage and topics_well_covered from evaluator answer_quality. Pure."""
    new_coverage = dict(session.signal_coverage)
    for sig in signals_present:
        current = new_coverage.get(sig, "none")
        if current == "none":
            new_coverage[sig] = "partial"
        elif current == "partial":
            new_coverage[sig] = "saturated"
        # saturated stays saturated

    new_topics = list(session.topics_well_covered)
    for topic in topics_touched:
        if topic not in new_topics:
            new_topics.append(topic)

    return session.model_copy(update={
        "signal_coverage": new_coverage,
        "topics_well_covered": new_topics,
    })


async def _call_evaluator_raw(
    question: QuestionEntry,
    answer_text: str,
    session: CreationSession,
) -> dict:
    """Make the bounded Groq evaluator call. Raises on any error — caller handles fallback.

    Creation-time only. Never called on the live reply path.
    """
    from config import settings  # noqa: PLC0415

    if settings.mock_mode:
        return {
            "answered": True,
            "answer_quality": {
                "depth": "adequate",
                "on_topic": True,
                "multi_topic": False,
                "topics_touched": [],
                "signals_present": [],
            },
            "next_action": "advance",
            "probe_id": None,
            "steer_id": None,
            "skip_reason": None,
            "confidence": 0.9,
        }

    await groq_acquire(interactive=True)

    payload = {
        "model": _EVALUATOR_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _EVALUATOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    _build_evaluator_input(question, answer_text, session)
                ),
            },
        ],
        "max_tokens": 512,
        "temperature": 0.1,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()

    return json.loads(resp.json()["choices"][0]["message"]["content"])


async def evaluate_next_action(
    session: CreationSession,
    question: QuestionEntry,
    answer_text: str,
) -> tuple[CreationSession, dict]:
    """Try the Groq evaluator (§4); fall back to §4.4 deterministic on any failure.

    Returns (updated_session, action_dict). Updates signal_coverage and
    topics_well_covered on success; leaves session unchanged on fallback.
    Creation-time only — never called on the live reply path.
    """
    try:
        raw = await _call_evaluator_raw(question, answer_text, session)
        action = _validate_evaluator_output(raw, question, session)
        if action is None:
            raise ValueError("evaluator output failed validation")

        answer_quality = raw.get("answer_quality") or {}
        signals_present = answer_quality.get("signals_present") or []
        topics_touched = answer_quality.get("topics_touched") or []
        session = _update_coverage(session, signals_present, topics_touched)

        logger.debug(
            "[evaluator] q=%s action=%s confidence=%.2f",
            question.id,
            action["next_action"],
            float(raw.get("confidence", 0.0)),
        )
        return session, action

    except Exception as exc:
        logger.warning("[evaluator] failed (%s) — using §4.4 deterministic fallback", exc)
        action = deterministic_next_action(
            session.followups_used_this_question,
            question.max_followups,
            answer_text,
            question,
        )
        return session, action


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

    session, action = await evaluate_next_action(session, question, answer_text)
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

    session, action = await evaluate_next_action(session, question, answer_text)
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
