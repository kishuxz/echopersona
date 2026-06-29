"""Live-path listener access resolution (spec §8.1.2, §9.3).

resolve_listener_context() is the single entry point for Step 6 auth on the
WebSocket path. Called once at connection time; returns a ListenerContext or
None to deny. Never inferred — always authenticated from DB records.

Access rules:
  - Active consent record must exist with text_twin=True.
  - Persona owner always gets access.
  - Beneficiaries get access only for activation_trigger="immediate".
  - posthumous_verified is denied — activation signal not yet wired.
"""
import logging

from models.consent import ConsentRecord, ListenerContext, ModalityConsent

logger = logging.getLogger(__name__)


async def get_active_consent_for_persona(db, persona_id: str) -> ConsentRecord | None:
    """Load the active consent record for a persona without an ownership check.

    Uses the service-role DB client — bypasses RLS intentionally (server-side).
    """
    result = (
        db.table("consent_records")
        .select("*")
        .eq("persona_id", persona_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )
    if result is None or not result.data:
        return None
    return ConsentRecord(**result.data)


async def resolve_listener_context(
    db, persona_id: str, user_id: str
) -> ListenerContext | None:
    """Return the listener's access context, or None if access is denied.

    Called once at WebSocket handshake time; result is stored per-session in ws.py.
    """
    # Gate 1: resolve persona; deny if not found
    persona_row = (
        db.table("personas")
        .select("user_id")
        .eq("id", persona_id)
        .maybe_single()
        .execute()
    )
    if persona_row is None or not persona_row.data:
        logger.info("[listener] denied %s on %s: persona not found", user_id, persona_id)
        return None

    # Gate 2: persona owner always allowed; consent used for modalities only
    if persona_row.data["user_id"] == user_id:
        consent = await get_active_consent_for_persona(db, persona_id)
        modalities = (
            consent.modality_consent
            if consent is not None and consent.modality_consent.text_twin
            else ModalityConsent()
        )
        return ListenerContext(
            listener_user_id=user_id,
            is_owner=True,
            allowed_modalities=modalities,
        )

    # Gate 3: non-owner requires active consent with text_twin=True
    consent = await get_active_consent_for_persona(db, persona_id)
    if consent is None or not consent.modality_consent.text_twin:
        logger.info(
            "[listener] denied %s on %s: no active consent or text_twin=False",
            user_id,
            persona_id,
        )
        return None

    # Gate 4: immediate beneficiary in active succession record
    succession_row = (
        db.table("succession_records")
        .select("beneficiaries")
        .eq("persona_id", persona_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )
    if succession_row is not None and succession_row.data:
        for b in succession_row.data.get("beneficiaries") or []:
            if b.get("user_id") == user_id:
                if b.get("activation_trigger") == "immediate":
                    # §9.3 — look up entity canonical for listener-aware retrieval biasing
                    rel_result = (
                        db.table("persona_relationships")
                        .select("entity_canonical")
                        .eq("persona_id", persona_id)
                        .eq("listener_user_id", user_id)
                        .maybe_single()
                        .execute()
                    )
                    rel_data = rel_result.data if rel_result is not None else None
                    return ListenerContext(
                        listener_user_id=user_id,
                        is_owner=False,
                        relationship=b.get("relationship"),
                        address_term=b.get("address_term") or None,
                        scope=b.get("scope"),
                        allowed_modalities=consent.modality_consent,
                        closeness_level=b.get("closeness_level"),
                        greeting_style=b.get("greeting_style"),
                        entity_canonical=rel_data.get("entity_canonical") if rel_data else None,
                    )
                # Found but not immediately activated
                logger.info(
                    "[listener] denied %s on %s: beneficiary activation_trigger=%s",
                    user_id,
                    persona_id,
                    b.get("activation_trigger"),
                )
                return None

    logger.info(
        "[listener] denied %s on %s: not owner, not in succession beneficiaries",
        user_id,
        persona_id,
    )
    return None
