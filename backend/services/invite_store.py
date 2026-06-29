"""DB operations for persona_invites.

Token is stored as plain text (32-byte URL-safe random). The UNIQUE constraint
on the token column is the collision guard. All accept-path lookups use the
service-role key so RLS is bypassed — the token itself is the credential.
"""
import secrets
from datetime import datetime, timezone
from typing import Optional

from services.db import get_db

_TOKEN_BYTES = 32


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(expires_at_str: str) -> bool:
    exp = datetime.fromisoformat(expires_at_str)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return _now_utc() >= exp


async def create_invite(
    persona_id: str,
    invited_by: str,
    email: str,
    relationship: str,
    entity_canonical: str,
    address_term: str,
) -> dict:
    """Insert a pending invite row. Returns the full row including the raw token."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    db = get_db()
    result = (
        db.table("persona_invites")
        .insert({
            "persona_id": persona_id,
            "invited_by": invited_by,
            "email": email,
            "relationship": relationship,
            "entity_canonical": entity_canonical,
            "address_term": address_term,
            "token": token,
            "status": "pending",
        })
        .execute()
    )
    # Return the inserted row merged with the raw token (token col is also in the row)
    return result.data[0]


async def get_invites_for_persona(persona_id: str) -> list[dict]:
    db = get_db()
    result = (
        db.table("persona_invites")
        .select("id,persona_id,email,relationship,status,expires_at,accepted_at,created_at")
        .eq("persona_id", persona_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


async def get_invite_by_id(invite_id: str, owner_user_id: str) -> Optional[dict]:
    """Return invite row only if the caller owns the persona it belongs to."""
    db = get_db()
    row = (
        db.table("persona_invites")
        .select("id,persona_id,status")
        .eq("id", invite_id)
        .maybe_single()
        .execute()
    )
    if not row.data:
        return None
    persona = (
        db.table("personas")
        .select("user_id")
        .eq("id", row.data["persona_id"])
        .maybe_single()
        .execute()
    )
    if not persona.data or persona.data["user_id"] != owner_user_id:
        return None
    return row.data


async def get_invite_by_token(token: str) -> Optional[dict]:
    db = get_db()
    result = (
        db.table("persona_invites")
        .select("*")
        .eq("token", token)
        .maybe_single()
        .execute()
    )
    return result.data


async def revoke_invite(invite_id: str) -> None:
    db = get_db()
    db.table("persona_invites").update({"status": "revoked"}).eq("id", invite_id).execute()


async def accept_invite(token: str, listener_user_id: str) -> Optional[dict]:
    """Validate token, mark accepted, upsert into persona_relationships.

    Returns the relationship summary dict, or None if the token is invalid/expired/used.
    """
    invite = await get_invite_by_token(token)
    if not invite:
        return None
    if invite["status"] != "pending":
        return None
    if _is_expired(invite["expires_at"]):
        return None
    if invite.get("accepted_at") is not None:
        return None

    db = get_db()

    db.table("persona_invites").update({
        "status": "accepted",
        "accepted_at": _now_utc().isoformat(),
        "listener_user_id": listener_user_id,
    }).eq("id", invite["id"]).execute()

    db.table("persona_relationships").upsert(
        {
            "persona_id": invite["persona_id"],
            "listener_user_id": listener_user_id,
            "entity_canonical": invite.get("entity_canonical", ""),
            "relationship": invite["relationship"],
            "address_term": invite.get("address_term", ""),
            "invite_id": invite["id"],
        },
        on_conflict="persona_id,listener_user_id",
    ).execute()

    return {
        "persona_id": invite["persona_id"],
        "relationship": invite["relationship"],
        "entity_canonical": invite.get("entity_canonical", ""),
    }


async def count_accepted_members(persona_id: str) -> int:
    """Count rows in persona_relationships for this persona (accepted family members)."""
    db = get_db()
    result = (
        db.table("persona_relationships")
        .select("id", count="exact")
        .eq("persona_id", persona_id)
        .execute()
    )
    return result.count or 0
