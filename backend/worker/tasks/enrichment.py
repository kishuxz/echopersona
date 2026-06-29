"""Per-persona enrichment task: Stage 3 (entity graph) + Stage 4 (style exemplars + voice card).

Triggered by the ingestion worker after units are written, and can also be run
standalone to refresh a persona's entity graph or style bank.
"""
import logging

from services.ingestion.source_store import get_memory_units_for_persona
from services.ingestion.stage3 import build_entity_graph
from services.ingestion.stage4 import extract_style_exemplars
from services.ingestion.stage4b import extract_identity_card
from services.persona_store import (
    update_entity_graph,
    update_identity_card,
    update_readiness_status,
    update_style_exemplars,
    update_voice_card,
)
from services.rag import PERSONAS, RAG_INDICES

logger = logging.getLogger(__name__)


async def enrich_persona(ctx: dict, persona_id: str) -> dict:
    """Run Stage 3 + Stage 4 for a persona, then invalidate its in-memory RAG index.

    Returns a summary dict with entity, exemplar, and voice_card counts.
    """
    logger.info("[Enrich] starting persona_id=%s", persona_id)

    # Load all units (prefer verified; fall back to all)
    units = await get_memory_units_for_persona(persona_id, verified_only=True)
    if not units:
        units = await get_memory_units_for_persona(persona_id, verified_only=False)

    if not units:
        logger.info("[Enrich] no memory units found for persona_id=%s, skipping", persona_id)
        return {"persona_id": persona_id, "status": "skipped", "reason": "no_units"}

    try:
        # Stage 3: entity coreference
        entity_graph = await build_entity_graph(units)
        await update_entity_graph(persona_id, entity_graph)
        logger.info("[Enrich] Stage 3 done — %d entities", len(entity_graph))

        # Stage 4: style exemplar bank + voice card (single Groq call)
        exemplars, voice_card = await extract_style_exemplars(units)
        await update_style_exemplars(persona_id, exemplars)
        await update_voice_card(persona_id, voice_card)
        logger.info(
            "[Enrich] Stage 4 done — %d exemplars, voice_card populated=%s",
            len(exemplars),
            bool(any(voice_card.values())),
        )

        # Stage 4B: identity card — isolated so a failure here does not block readiness
        identity_card: dict = {}
        try:
            identity_card = await extract_identity_card(units)
            await update_identity_card(persona_id, identity_card)
            logger.info(
                "[Enrich] Stage 4B done — identity_card populated=%s",
                bool(any(identity_card.values())),
            )
        except Exception as ic_exc:
            logger.warning("[Enrich] Stage 4B failed, continuing without identity_card: %s", ic_exc)

        # Invalidate in-memory caches so the next WS session sees fresh data
        RAG_INDICES.pop(persona_id, None)
        PERSONAS.pop(persona_id, None)
        logger.info("[Enrich] caches invalidated for persona_id=%s", persona_id)

        await update_readiness_status(persona_id, "ready")
        logger.info("[Enrich] readiness_status=ready for persona_id=%s", persona_id)

        return {
            "persona_id": persona_id,
            "status": "done",
            "entity_count": len(entity_graph),
            "exemplar_count": len(exemplars),
            "voice_card_populated": bool(any(voice_card.values())),
            "identity_card_populated": bool(any(identity_card.values())),
        }

    except Exception as exc:
        logger.error("[Enrich] failed persona_id=%s: %s", persona_id, exc, exc_info=True)
        try:
            await update_readiness_status(persona_id, "failed")
        except Exception as rs_exc:
            logger.warning("[Enrich] could not update readiness to failed: %s", rs_exc)
        return {"persona_id": persona_id, "status": "error", "reason": str(exc)}
