"""Ingestion pipeline tasks — Stages 0 → 1 → 2 → Fidelity.

Stage 0 — normalize + stamp provenance          (stage0.py)
Stage 1 — episode segmentation                  (stage1.py)
Stage 2 — persona-conditioned first-person transform (stage2.py)
Fidelity — verify each unit vs its source span  (fidelity.py)
"""
import logging

from services.ingestion.fidelity import verify_fidelity
from services.ingestion.source_store import (
    download_source_file,
    get_memory_unit,
    get_source_record,
    update_source_status,
    update_unit_fidelity,
    write_memory_unit,
)
from services.ingestion.stage0 import normalize_source
from services.ingestion.stage1 import segment_episodes
from services.ingestion.stage2 import transform_episode

logger = logging.getLogger(__name__)

_FILE_MODALITIES = {"audio", "video", "document", "photo", "letter"}

_EXT_TO_MIME: dict[str, str] = {
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "mp3": "audio/mpeg",
    "m4a": "audio/x-m4a",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "pdf": "application/pdf",
}


def _mime_from_path(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _EXT_TO_MIME.get(ext, "application/octet-stream")


def _source_meta(record: dict, timestamp_range: tuple[float, float]) -> dict:
    return {
        "modality": record.get("modality", ""),
        "question_category": record.get("question_category", ""),
        "question_text": record.get("question_text", ""),
        "source_question_id": record.get("source_question_id", ""),
        "source_type": record.get("source_type", "answer"),
        "file_id": record.get("file_id", ""),
        "media_ref": record.get("media_ref", ""),
        "group_name": record.get("group_name", ""),
        "timestamp_range": list(timestamp_range),
        "captured_at": record.get("captured_at", ""),
    }


async def _run_pipeline(
    ctx: dict,
    record: dict,
    user_id: str,
    version: int = 1,
    supersedes: str | None = None,
) -> dict:
    """Core ingestion pipeline: normalize → segment → transform → fidelity → write.

    version/supersedes are forwarded to write_memory_unit so corrections can
    carry supersedes=<replaced_unit_id> and version=replaced.version+1 (§6/§7.1).
    """
    source_id: str = record["id"]
    await update_source_status(source_id, "processing")

    try:
        # ── Stage 0: normalize ──────────────────────────────────────────────
        modality = record["modality"]
        file_bytes: bytes | None = None
        file_id: str = record.get("file_id", "")

        if modality.lower() in _FILE_MODALITIES and file_id:
            file_bytes = await download_source_file(file_id)

        raw_text, timestamp_range = await normalize_source(
            modality=modality,
            text_content=record.get("text_content", ""),
            file_bytes=file_bytes,
            filename=file_id.split("/")[-1] if file_id else "upload",
            content_type=_mime_from_path(file_id),
        )

        await update_source_status(source_id, "stage0_complete", raw_text, timestamp_range)
        logger.info("[Pipeline] Stage 0 done source_id=%s raw_len=%d", source_id, len(raw_text))

        if not raw_text.strip():
            await update_source_status(source_id, "done")
            return {"source_id": source_id, "status": "done", "units_created": 0}

        # ── Stage 1: episode segmentation ───────────────────────────────────
        episodes = await segment_episodes(raw_text)
        await update_source_status(source_id, "stage1_complete")
        logger.info("[Pipeline] Stage 1 done source_id=%s episodes=%d", source_id, len(episodes))

        # ── Stage 2 + Fidelity: per-episode ─────────────────────────────────
        persona_id: str = record.get("persona_id", "")
        source_meta = _source_meta(record, timestamp_range)
        units_created: list[str] = []

        for i, episode in enumerate(episodes):
            try:
                unit_data = await transform_episode(episode, record)
                logger.info(
                    "[Pipeline] Stage 2 done source_id=%s episode=%d/%d",
                    source_id, i + 1, len(episodes),
                )

                unit_id = await write_memory_unit(
                    user_id=user_id,
                    persona_id=persona_id,
                    source_id=source_id,
                    source_meta=source_meta,
                    content_first_person=unit_data["content_first_person"],
                    memory_category=unit_data.get("memory_category", "episodic"),
                    stance=unit_data["stance"],
                    affect=unit_data["affect"],
                    themes=unit_data["themes"],
                    entities=unit_data["entities"],
                    version=version,
                    supersedes=supersedes,
                )

                fidelity = await verify_fidelity(
                    source_episode_text=episode["episode_text"],
                    content_first_person=unit_data["content_first_person"],
                )
                await update_unit_fidelity(
                    unit_id=unit_id,
                    fidelity_flags=fidelity["flags"],
                    fidelity_score=fidelity["fidelity_score"],
                )
                if fidelity["has_additions"]:
                    logger.warning(
                        "[Pipeline] Fidelity flags on unit_id=%s score=%.2f flags=%d",
                        unit_id, fidelity["fidelity_score"], len(fidelity["flags"]),
                    )

                units_created.append(unit_id)

            except Exception as ep_exc:
                logger.error(
                    "[Pipeline] Episode %d/%d failed source_id=%s: %s",
                    i + 1, len(episodes), source_id, ep_exc, exc_info=True,
                )

        await update_source_status(source_id, "done")
        logger.info(
            "[Pipeline] done source_id=%s units_created=%d", source_id, len(units_created)
        )

        if persona_id and units_created:
            try:
                await ctx["redis"].enqueue_job("enrich_persona", persona_id)
                logger.info("[Pipeline] enqueued enrich_persona for persona_id=%s", persona_id)
            except Exception as enrich_exc:
                logger.warning("[Pipeline] could not enqueue enrichment: %s", enrich_exc)

        return {
            "source_id": source_id,
            "status": "done",
            "units_created": len(units_created),
            "unit_ids": units_created,
        }

    except Exception as exc:
        logger.error("Pipeline failed source_id=%s: %s", source_id, exc, exc_info=True)
        await update_source_status(source_id, "error")
        return {"source_id": source_id, "status": "error", "reason": str(exc)}


async def ingest_memory_unit(ctx: dict, source_id: str, user_id: str) -> dict:
    """Full ingestion pipeline for one source item (answers)."""
    record = await get_source_record(source_id)
    if not record:
        logger.error("Source record not found: %s", source_id)
        return {"source_id": source_id, "status": "error", "reason": "record_not_found"}
    return await _run_pipeline(ctx, record, user_id, version=1, supersedes=None)


async def ingest_correction_unit(
    ctx: dict,
    source_id: str,
    user_id: str,
    supersedes_unit_id: str,
) -> dict:
    """Ingestion pipeline for a wrong_fact correction (§7.1).

    Identical pipeline to ingest_memory_unit, but the produced units carry
    supersedes=<replaced_unit_id> and version=replaced.version+1.
    The replaced unit stays in the DB for audit; live retrieval excludes it
    via get_memory_units_for_persona(exclude_superseded=True).
    """
    record = await get_source_record(source_id)
    if not record:
        logger.error("Source record not found: %s", source_id)
        return {"source_id": source_id, "status": "error", "reason": "record_not_found"}

    superseded = await get_memory_unit(supersedes_unit_id)
    if not superseded:
        logger.error("Superseded unit not found: %s", supersedes_unit_id)
        return {
            "source_id": source_id,
            "status": "error",
            "reason": "superseded_unit_not_found",
        }

    new_version = superseded.get("version", 1) + 1
    logger.info(
        "[Pipeline] correction source_id=%s supersedes=%s new_version=%d",
        source_id, supersedes_unit_id, new_version,
    )
    return await _run_pipeline(
        ctx, record, user_id, version=new_version, supersedes=supersedes_unit_id
    )
