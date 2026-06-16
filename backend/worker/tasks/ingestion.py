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
        "file_id": record.get("file_id", ""),
        "group_name": record.get("group_name", ""),
        "timestamp_range": list(timestamp_range),
    }


async def ingest_memory_unit(ctx: dict, source_id: str, user_id: str) -> dict:
    """Full ingestion pipeline for one source item."""
    record = await get_source_record(source_id)
    if not record:
        logger.error("Source record not found: %s", source_id)
        return {"source_id": source_id, "status": "error", "reason": "record_not_found"}

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
                # Stage 2: persona-conditioned transform
                unit_data = await transform_episode(episode, record)
                logger.info(
                    "[Pipeline] Stage 2 done source_id=%s episode=%d/%d",
                    source_id, i + 1, len(episodes),
                )

                # Write memory unit (verified=False by default)
                unit_id = await write_memory_unit(
                    user_id=user_id,
                    persona_id=persona_id,
                    source_id=source_id,
                    source_meta=source_meta,
                    content_first_person=unit_data["content_first_person"],
                    stance=unit_data["stance"],
                    affect=unit_data["affect"],
                    themes=unit_data["themes"],
                    entities=unit_data["entities"],
                )

                # Fidelity verification
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

        # Kick off per-persona enrichment (Stage 3 entity graph + Stage 4 style exemplars)
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
