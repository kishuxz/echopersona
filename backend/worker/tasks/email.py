"""arq task: fan out readiness notification emails to all linked family members.

Enqueued by enrich_persona immediately after readiness_status is set to 'ready'.
Best-effort — exceptions are caught and logged, never re-raised.
"""
import logging

from services import email as email_service
from services.db import get_db

logger = logging.getLogger(__name__)


async def send_readiness_emails(ctx: dict, persona_id: str) -> dict:
    db = get_db()
    try:
        persona_row = (
            db.table("personas")
            .select("name")
            .eq("id", persona_id)
            .maybe_single()
            .execute()
        )
        if not persona_row.data:
            logger.warning("[Email] persona not found for readiness notification: %s", persona_id)
            return {"sent": 0}
        persona_name = persona_row.data["name"]

        members = (
            db.table("persona_relationships")
            .select("listener_user_id")
            .eq("persona_id", persona_id)
            .execute()
        )
        if not members.data:
            return {"sent": 0}

        sent = 0
        for row in members.data:
            uid = row.get("listener_user_id")
            if not uid:
                continue
            try:
                user_resp = db.auth.admin.get_user_by_id(uid)
                member_email = user_resp.user.email if user_resp.user else None
                if member_email:
                    ok = await email_service.send_readiness_notification(
                        to_email=member_email,
                        persona_name=persona_name,
                        persona_id=persona_id,
                    )
                    if ok:
                        sent += 1
            except Exception as exc:
                logger.warning("[Email] could not notify member %s: %s", uid, exc)

        logger.info("[Email] sent %d readiness notifications for persona %s", sent, persona_id)
        return {"sent": sent}

    except Exception as exc:
        logger.warning("[Email] readiness fan-out failed for persona %s: %s", persona_id, exc)
        return {"sent": 0, "error": str(exc)}
