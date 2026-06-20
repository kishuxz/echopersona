"""Per-persona enrichment task: Stage 3 (entity graph) + Stage 4 (style card).

Triggered by the ingestion worker after units are written, and can also be run
standalone to refresh a persona's entity graph or style bank.
"""
import logging

from services.ingestion.source_store import get_memory_units_for_persona
from services.ingestion.stage3 import build_entity_graph
from services.ingestion.stage4 import extract_style_card
from services.persona_store import update_entity_graph, update_style_card
from services.rag import RAG_INDICES

logger = logging.getLogger(__name__)


async def enrich_persona(ctx: dict, persona_id: str) -> dict:
    """Run Stage 3 + Stage 4 for a persona, then invalidate its in-memory RAG index.

    Returns a summary dict with entity and exemplar counts.
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

        # Stage 4: full style card (exemplars + tone + avoid_phrases + length pref + relationship_tone)
        style_card = await extract_style_card(units)
        await update_style_card(persona_id, style_card)
        logger.info(
            "[Enrich] Stage 4 done — %d exemplars, tone=%r",
            len(style_card["style_exemplars"]),
            style_card["tone"],
        )

        # Invalidate in-memory RAG index so the next WS session rebuilds from new units
        RAG_INDICES.pop(persona_id, None)
        logger.info("[Enrich] RAG index invalidated for persona_id=%s", persona_id)

        return {
            "persona_id": persona_id,
            "status": "done",
            "entity_count": len(entity_graph),
            "exemplar_count": len(style_card["style_exemplars"]),
        }

    except Exception as exc:
        logger.error("[Enrich] failed persona_id=%s: %s", persona_id, exc, exc_info=True)
        return {"persona_id": persona_id, "status": "error", "reason": str(exc)}
