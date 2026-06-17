"""Self-review / correction loop endpoints — PERSONA_SPEC.md §7.1."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from middleware.auth import get_current_user
from services.ingestion.source_store import create_source_record, get_memory_unit
from services.persona_store import get_persona

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review", tags=["review"])

_VALID_FLAG_TYPES = frozenset({"wrong_fact", "wrong_tone", "missing", "good"})


class FlagRequest(BaseModel):
    flag_type: str                   # wrong_fact | wrong_tone | missing | good
    unit_id: str | None = None       # required for wrong_fact; identifies the offending unit
    correction_text: str | None = None  # required for wrong_fact
    question_category: str | None = None  # optional context for missing


@router.post("/{persona_id}/flag")
async def flag_reply(
    persona_id: str,
    request: Request,
    body: FlagRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """Flag a twin reply. Routing per §7.1:
    - good        → positive signal, no-op
    - wrong_tone  → log for Stage 4 style-exemplar tuning (no tuning logic yet)
    - missing     → log a gap report (no re-prompt logic yet)
    - wrong_fact  → correction pipeline: capture correction text and re-ingest
    """
    if body.flag_type not in _VALID_FLAG_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"flag_type must be one of {sorted(_VALID_FLAG_TYPES)}",
        )

    persona = await get_persona(persona_id, user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    if body.flag_type == "good":
        return {"flag_type": "good", "action": "none"}

    if body.flag_type == "wrong_tone":
        logger.info(
            "[review] wrong_tone flag persona=%s unit=%s user=%s",
            persona_id, body.unit_id, user_id,
        )
        return {"flag_type": "wrong_tone", "action": "logged"}

    if body.flag_type == "missing":
        logger.info(
            "[review] missing gap report persona=%s category=%s user=%s",
            persona_id, body.question_category, user_id,
        )
        return {"flag_type": "missing", "action": "logged"}

    # ── wrong_fact: correction pipeline ─────────────────────────────────────
    if not body.unit_id:
        raise HTTPException(status_code=400, detail="unit_id required for wrong_fact")
    if not body.correction_text or not body.correction_text.strip():
        raise HTTPException(status_code=400, detail="correction_text required for wrong_fact")

    target_unit = await get_memory_unit(body.unit_id)
    if not target_unit:
        raise HTTPException(status_code=404, detail=f"unit_id {body.unit_id!r} not found")

    if target_unit.get("persona_id") != persona_id:
        raise HTTPException(status_code=404, detail=f"unit_id {body.unit_id!r} not found")

    # Inherit provenance from the unit being corrected so the correction traces
    # back to the same question/topic (§6).
    src = target_unit.get("source") or {}
    source_id = await create_source_record(
        user_id=user_id,
        persona_id=persona_id,
        modality="text",
        question_category=src.get("question_category", ""),
        question_text=src.get("question_text", ""),
        group_name=src.get("group_name", ""),
        file_id="",
        text_content=body.correction_text.strip(),
        source_question_id=src.get("source_question_id", ""),
        source_type="correction",
        media_ref="",
    )

    arq_pool = request.app.state.arq_pool
    job = await arq_pool.enqueue_job(
        "ingest_correction_unit", source_id, user_id, body.unit_id
    )
    job_id = job.job_id if job else None

    logger.info(
        "[review] wrong_fact correction queued source_id=%s supersedes=%s job_id=%s",
        source_id, body.unit_id, job_id,
    )
    return {
        "flag_type": "wrong_fact",
        "action": "correction_queued",
        "source_id": source_id,
        "supersedes_unit_id": body.unit_id,
        "job_id": job_id,
    }
