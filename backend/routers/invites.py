"""Invite flow endpoints.

POST   /invites/{persona_id}   — owner creates an invite for a family member
GET    /invites/{persona_id}   — owner lists all invites for a persona
DELETE /invites/{invite_id}    — owner revokes a pending invite
POST   /invites/accept         — invitee accepts a magic-link token (JWT required)
"""
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from middleware.auth import get_current_user
from models.invite import AcceptInviteRequest, AcceptInviteResponse, InviteCreate, InviteRecord
from services import email as email_service
from services import invite_store
from services.db import get_db
from services.entitlements import can_add_family_member, get_entitlement_for_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/invites", tags=["invites"])


def _require_persona_owner(persona_id: str, user_id: str) -> dict:
    """Return persona row or raise 404/403."""
    db = get_db()
    row = (
        db.table("personas")
        .select("id,name,user_id")
        .eq("id", persona_id)
        .maybe_single()
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="Persona not found")
    if row.data["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your persona")
    return row.data


# ── Create invite ────────────────────────────────────────────────────────────

@router.post("/{persona_id}", status_code=201, response_model=InviteRecord)
async def create_invite(
    persona_id: str,
    body: InviteCreate,
    background_tasks: BackgroundTasks,
    user: Annotated[dict, Depends(get_current_user)],
):
    uid = user["sub"]
    persona = _require_persona_owner(persona_id, uid)

    db = get_db()
    entitlement = await get_entitlement_for_user(db, uid)
    current_count = await invite_store.count_accepted_members(persona_id)
    decision = can_add_family_member(entitlement, current_count)
    if not decision.allowed:
        raise HTTPException(status_code=402, detail=decision.reason)

    invite = await invite_store.create_invite(
        persona_id=persona_id,
        invited_by=uid,
        email=str(body.email),
        relationship=body.relationship,
        entity_canonical=body.entity_canonical,
        address_term=body.address_term,
    )

    background_tasks.add_task(
        email_service.send_invite_email,
        to_email=str(body.email),
        inviter_name=user.get("email", "Someone"),
        persona_name=persona["name"],
        token=invite["token"],
    )

    return InviteRecord(**{k: v for k, v in invite.items() if k != "token"})


# ── List invites ─────────────────────────────────────────────────────────────

@router.get("/{persona_id}", response_model=list[InviteRecord])
async def list_invites(
    persona_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    uid = user["sub"]
    _require_persona_owner(persona_id, uid)
    rows = await invite_store.get_invites_for_persona(persona_id)
    return [InviteRecord(**r) for r in rows]


# ── Revoke invite ────────────────────────────────────────────────────────────

@router.delete("/{invite_id}", status_code=200)
async def revoke_invite(
    invite_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    uid = user["sub"]
    invite = await invite_store.get_invite_by_id(invite_id, uid)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    await invite_store.revoke_invite(invite_id)
    return {"revoked": True}


# ── Accept invite ────────────────────────────────────────────────────────────

@router.post("/accept", status_code=200, response_model=AcceptInviteResponse)
async def accept_invite(
    body: AcceptInviteRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[dict, Depends(get_current_user)],
):
    uid = user["sub"]

    invite_row = await invite_store.get_invite_by_token(body.token)
    if not invite_row or invite_row["status"] != "pending":
        raise HTTPException(status_code=410, detail="Invite is no longer valid")

    db = get_db()
    persona_row = (
        db.table("personas")
        .select("user_id,name")
        .eq("id", invite_row["persona_id"])
        .maybe_single()
        .execute()
    )
    if not persona_row.data:
        raise HTTPException(status_code=404, detail="Persona not found")

    owner_uid = persona_row.data["user_id"]
    persona_name = persona_row.data["name"]

    # Re-check entitlement at acceptance (covers plan downgrade between invite and accept)
    owner_entitlement = await get_entitlement_for_user(db, owner_uid)
    current_count = await invite_store.count_accepted_members(invite_row["persona_id"])
    decision = can_add_family_member(owner_entitlement, current_count)
    if not decision.allowed:
        raise HTTPException(status_code=402, detail=decision.reason)

    result = await invite_store.accept_invite(body.token, uid)
    if result is None:
        raise HTTPException(status_code=410, detail="Invite expired or already used")

    # Notify persona owner (best-effort)
    invitee_email = user.get("email", "")
    if invitee_email:
        try:
            owner_resp = db.auth.admin.get_user_by_id(owner_uid)
            owner_email = owner_resp.user.email if owner_resp.user else None
            if owner_email:
                background_tasks.add_task(
                    email_service.send_acceptance_confirmation,
                    to_email=owner_email,
                    persona_name=persona_name,
                    member_email=invitee_email,
                )
        except Exception as exc:
            logger.warning("could not look up owner email for acceptance confirmation: %s", exc)

    return AcceptInviteResponse(**result)
