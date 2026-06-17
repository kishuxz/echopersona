import logging
from datetime import datetime, timezone

from models.consent import (
    ConsentCreate,
    ConsentRecord,
    SuccessionCreate,
    SuccessionRecord,
)

logger = logging.getLogger(__name__)


def ensure_persona_owner(db, persona_id: str, user_id: str) -> bool:
    result = (
        db.table("personas")
        .select("id")
        .eq("id", persona_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return bool(result.data)


async def get_active_consent_record(
    db, persona_id: str, user_id: str
) -> ConsentRecord | None:
    if not ensure_persona_owner(db, persona_id, user_id):
        return None
    result = (
        db.table("consent_records")
        .select("*")
        .eq("persona_id", persona_id)
        .eq("subject_user_id", user_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )
    if not result.data:
        return None
    return ConsentRecord(**result.data)


async def write_consent_record(
    db, persona_id: str, user_id: str, payload: ConsentCreate
) -> ConsentRecord | None:
    if not ensure_persona_owner(db, persona_id, user_id):
        return None

    existing = (
        db.table("consent_records")
        .select("id, consent_version")
        .eq("persona_id", persona_id)
        .eq("subject_user_id", user_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )

    now = datetime.now(timezone.utc).isoformat()
    new_version = 1
    supersedes = None

    if existing.data:
        old_id = existing.data["id"]
        new_version = existing.data["consent_version"] + 1
        supersedes = old_id
        db.table("consent_records").update(
            {"status": "superseded", "ended_at": now}
        ).eq("id", old_id).execute()

    new_row: dict = {
        "persona_id": persona_id,
        "subject_user_id": user_id,
        "status": "active",
        "consent_version": new_version,
        "policy_version": payload.policy_version,
        "modality_consent": payload.modality_consent.model_dump(),
        "rights": payload.rights.model_dump(),
        "affirmation_media_ref": payload.affirmation_media_ref,
    }
    if supersedes:
        new_row["supersedes"] = supersedes

    result = db.table("consent_records").insert(new_row).execute()
    if not result.data:
        raise RuntimeError("Failed to write consent record")
    return ConsentRecord(**result.data[0])


async def get_active_succession_record(
    db, persona_id: str, user_id: str
) -> SuccessionRecord | None:
    if not ensure_persona_owner(db, persona_id, user_id):
        return None
    result = (
        db.table("succession_records")
        .select("*")
        .eq("persona_id", persona_id)
        .eq("subject_user_id", user_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )
    if not result.data:
        return None
    return SuccessionRecord(**result.data)


async def write_succession_record(
    db, persona_id: str, user_id: str, payload: SuccessionCreate
) -> SuccessionRecord | None:
    if not ensure_persona_owner(db, persona_id, user_id):
        return None

    existing = (
        db.table("succession_records")
        .select("id")
        .eq("persona_id", persona_id)
        .eq("subject_user_id", user_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )

    now = datetime.now(timezone.utc).isoformat()
    supersedes = None

    if existing.data:
        old_id = existing.data["id"]
        supersedes = old_id
        db.table("succession_records").update(
            {"status": "superseded", "ended_at": now}
        ).eq("id", old_id).execute()

    new_row: dict = {
        "persona_id": persona_id,
        "subject_user_id": user_id,
        "status": "active",
        "beneficiaries": [b.model_dump() for b in payload.beneficiaries],
    }
    if supersedes:
        new_row["supersedes"] = supersedes

    result = db.table("succession_records").insert(new_row).execute()
    if not result.data:
        raise RuntimeError("Failed to write succession record")
    return SuccessionRecord(**result.data[0])
