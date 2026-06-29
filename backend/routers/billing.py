import logging
from typing import Literal

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from config import settings
from middleware.auth import get_current_user
from models.entitlements import BillingStatusResponse, PersonaAccessDecision
from services.billing import create_checkout_session
from services.db import get_db
from services.entitlements import (
    can_add_family_member,
    can_use_chat,
    can_use_video,
    can_use_voice,
    family_member_limit_for_tier,
    get_entitlement_for_user,
)
from services.preservation import (
    can_access_posthumous,
    can_access_preserved_persona,
    get_posthumous_subscription,
    get_preservation_for_persona,
)
from services.stripe_webhooks import process_stripe_event, record_event_idempotent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

# Maps plan_tier values to config attribute names — price IDs never come from the client.
_PLAN_PRICE_MAP: dict[str, str] = {
    "creator": "stripe_price_creator_monthly",
    "legacy": "stripe_price_legacy_monthly",
    "preservation": "stripe_price_preservation_onetime",
}


class CheckoutRequest(BaseModel):
    plan_tier: Literal["creator", "legacy", "preservation"]
    persona_id: str | None = None  # required for preservation tier


class PreservationCheckoutRequest(BaseModel):
    persona_id: str


class PosthumousCheckoutRequest(BaseModel):
    persona_id: str


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class PreservationStatusResponse(BaseModel):
    persona_id: str
    preservation_locked: bool
    can_use_posthumous_chat: bool


@router.post("/checkout", response_model=CheckoutResponse)
async def start_checkout(
    body: CheckoutRequest,
    user_id: str = Depends(get_current_user),
) -> CheckoutResponse:
    if body.plan_tier == "preservation" and not body.persona_id:
        raise HTTPException(
            status_code=422,
            detail="persona_id is required when purchasing the Preservation plan.",
        )

    price_id: str = getattr(settings, _PLAN_PRICE_MAP[body.plan_tier], "")
    if not price_id:
        raise HTTPException(
            status_code=500,
            detail=f"Stripe price ID for plan '{body.plan_tier}' is not configured.",
        )

    db = get_db()
    if body.plan_tier == "preservation":
        checkout_mode = "payment"
        extra = {"purchase_type": "preservation", "persona_id": body.persona_id}
    else:
        checkout_mode = "subscription"
        extra = None
    result = await create_checkout_session(
        db=db,
        user_id=user_id,
        price_id=price_id,
        success_url=settings.frontend_billing_success_url,
        cancel_url=settings.frontend_billing_cancel_url,
        mode=checkout_mode,
        extra_metadata=extra,
    )
    return CheckoutResponse(checkout_url=result["checkout_url"], session_id=result["session_id"])


@router.post("/checkout/preservation", response_model=CheckoutResponse)
async def start_preservation_checkout(
    body: PreservationCheckoutRequest,
    user_id: str = Depends(get_current_user),
) -> CheckoutResponse:
    if not body.persona_id:
        raise HTTPException(status_code=422, detail="persona_id is required.")
    price_id = settings.stripe_price_preservation_onetime
    if not price_id:
        raise HTTPException(status_code=500, detail="Preservation price ID is not configured.")

    db = get_db()
    result = await create_checkout_session(
        db=db,
        user_id=user_id,
        price_id=price_id,
        success_url=settings.frontend_billing_success_url,
        cancel_url=settings.frontend_billing_cancel_url,
        mode="payment",
        extra_metadata={"purchase_type": "preservation", "persona_id": body.persona_id},
    )
    return CheckoutResponse(checkout_url=result["checkout_url"], session_id=result["session_id"])


@router.post("/checkout/posthumous", response_model=CheckoutResponse)
async def start_posthumous_checkout(
    body: PosthumousCheckoutRequest,
    user_id: str = Depends(get_current_user),
) -> CheckoutResponse:
    if not body.persona_id:
        raise HTTPException(status_code=422, detail="persona_id is required.")
    price_id = settings.stripe_price_posthumous_monthly
    if not price_id:
        raise HTTPException(status_code=500, detail="Posthumous access price ID is not configured.")

    db = get_db()
    result = await create_checkout_session(
        db=db,
        user_id=user_id,
        price_id=price_id,
        success_url=settings.frontend_billing_success_url,
        cancel_url=settings.frontend_billing_cancel_url,
        mode="subscription",
        extra_metadata={"purchase_type": "posthumous_access", "persona_id": body.persona_id},
    )
    return CheckoutResponse(checkout_url=result["checkout_url"], session_id=result["session_id"])


@router.get("/preservation/{persona_id}", response_model=PreservationStatusResponse)
async def get_preservation_status(
    persona_id: str,
    user_id: str = Depends(get_current_user),
) -> PreservationStatusResponse:
    """Return preservation lock and posthumous access status for a specific persona."""
    db = get_db()
    preservation = await get_preservation_for_persona(db, persona_id)
    posthumous = await get_posthumous_subscription(db, persona_id, user_id)
    return PreservationStatusResponse(
        persona_id=persona_id,
        preservation_locked=can_access_preserved_persona(preservation),
        can_use_posthumous_chat=can_access_posthumous(posthumous),
    )


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict:
    """Receive and process Stripe webhook events.

    Authentication is via Stripe-Signature header — no JWT required.
    Idempotency is enforced by stripe_webhook_events.stripe_event_id unique constraint.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature.")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook payload.")

    db = get_db()
    is_new = await record_event_idempotent(db, event.id, event.type)
    if not is_new:
        return {"status": "ok"}  # duplicate delivery — already processed

    await process_stripe_event(db, event)
    return {"status": "ok"}


@router.get("/status", response_model=BillingStatusResponse)
async def get_billing_status(
    user_id: str = Depends(get_current_user),
) -> BillingStatusResponse:
    """Return the authenticated user's current entitlement and access flags.

    No Stripe API calls — reads only from the stripe_entitlements table.
    Returns safe free-tier defaults when no entitlement row exists.
    """
    db = get_db()
    entitlement = await get_entitlement_for_user(db, user_id)
    plan_tier = entitlement.plan_tier if entitlement else "free"

    # Check preservation lock for any of the user's personas.
    preservation_locked = False
    try:
        lock_result = (
            db.table("preservation_locks")
            .select("id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        preservation_locked = bool(lock_result.data)
    except Exception:
        pass

    return BillingStatusResponse(
        plan_tier=plan_tier,
        status=entitlement.status if entitlement else None,
        can_use_chat=can_use_chat(entitlement),
        can_use_voice=can_use_voice(entitlement),
        can_use_video=can_use_video(entitlement),
        current_period_end=entitlement.current_period_end if entitlement else None,
        cancel_at_period_end=entitlement.cancel_at_period_end if entitlement else False,
        family_member_limit=family_member_limit_for_tier(plan_tier),
        is_preservation_locked=preservation_locked,
    )


@router.get("/persona/{persona_id}/access", response_model=PersonaAccessDecision)
async def get_persona_access(
    persona_id: str,
    user_id: str = Depends(get_current_user),
) -> PersonaAccessDecision:
    """Return combined entitlement + persona-state access decision for a specific persona.

    Used by the frontend to render mode availability (chat/voice/video) and family member quota.
    """
    db = get_db()

    # Load persona — must belong to the requesting user.
    persona_result = (
        db.table("personas")
        .select("user_id, voice_id, answer_count")
        .eq("id", persona_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not persona_result.data:
        raise HTTPException(status_code=404, detail="Persona not found.")

    persona_data = persona_result.data
    answer_count: int = persona_data.get("answer_count", 0)
    voice_id: str | None = persona_data.get("voice_id")

    entitlement = await get_entitlement_for_user(db, user_id)

    # Family member count.
    family_count_result = (
        db.table("persona_relationships")
        .select("id", count="exact")
        .eq("persona_id", persona_id)
        .execute()
    )
    family_member_count: int = family_count_result.count or 0

    # Preservation lock.
    lock_result = (
        db.table("preservation_locks")
        .select("tier_at_lock")
        .eq("persona_id", persona_id)
        .maybe_single()
        .execute()
    )
    is_preservation_locked = bool(lock_result.data)

    plan_tier = entitlement.plan_tier if entitlement else "free"
    limit = family_member_limit_for_tier(plan_tier)

    add_member_decision = can_add_family_member(entitlement, family_member_count)

    return PersonaAccessDecision(
        persona_id=persona_id,
        can_use_chat=can_use_chat(entitlement, answer_count=answer_count, is_owner=True),
        can_use_voice=can_use_voice(entitlement, answer_count=answer_count, voice_id=voice_id),
        can_use_video=can_use_video(entitlement, answer_count=answer_count),
        can_add_family_member=add_member_decision.allowed,
        family_member_limit=limit,
        family_member_count=family_member_count,
        answer_count=answer_count,
        is_preservation_locked=is_preservation_locked,
        voice_id_present=bool(voice_id),
    )
