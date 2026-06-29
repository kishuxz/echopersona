from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from config import settings
from models.entitlements import AccessDecision, StripeEntitlement

if TYPE_CHECKING:
    from supabase import Client

_TABLE = "stripe_entitlements"
_PAID_STATUSES: frozenset[str] = frozenset({"active", "trialing"})

# Sentinel: caller did not provide voice_id — skip the no-stock-voice check.
# Used to distinguish "plan capability" calls (no voice_id) from "runtime" calls (voice_id given).
_VOICE_ID_NOT_SET: object = object()

# Q&A answer thresholds that gate feature access (migration 011).
# Enforcement is flag-gated by ENFORCE_ANSWER_QUOTAS; existing personas default to 0.
FREE_QUESTION_LIMIT: int = 30       # text chat owner preview
VOICE_QUESTION_THRESHOLD: int = 60  # voice clone + voice chat
VIDEO_QUESTION_THRESHOLD: int = 90  # video chat + rich retrieval

# Family member limits per tier. None = unlimited.
_FAMILY_LIMITS: dict[str, int | None] = {
    "free": 0,
    "creator": 3,
    "legacy": None,
    "preservation": None,  # inherits tier_at_lock; resolved by the calling route
}


async def get_entitlement_for_user(db: "Client", user_id: str) -> StripeEntitlement | None:
    """Return the entitlement row for user_id, or None (= free tier with no subscription)."""
    result = (
        db.table(_TABLE)
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if result is None or not result.data:
        return None
    return StripeEntitlement(**result.data)


async def get_entitlement_by_customer_or_subscription(
    db: "Client",
    stripe_customer_id: str | None,
    stripe_subscription_id: str | None,
) -> StripeEntitlement | None:
    """Find an entitlement by Stripe customer ID, falling back to subscription ID."""
    if stripe_customer_id:
        result = (
            db.table(_TABLE)
            .select("*")
            .eq("stripe_customer_id", stripe_customer_id)
            .maybe_single()
            .execute()
        )
        if result.data:
            return StripeEntitlement(**result.data)

    if stripe_subscription_id:
        result = (
            db.table(_TABLE)
            .select("*")
            .eq("stripe_subscription_id", stripe_subscription_id)
            .maybe_single()
            .execute()
        )
        if result.data:
            return StripeEntitlement(**result.data)

    return None


async def upsert_entitlement_from_subscription(
    db: "Client",
    user_id: str,
    stripe_customer_id: str,
    stripe_subscription_id: str | None,
    plan_tier: str,
    status: str,
    current_period_end: datetime | None,
    cancel_at_period_end: bool = False,
    stripe_payment_intent_id: str | None = None,
) -> None:
    """Create or update the entitlement row for user_id.
    Called exclusively by the Stripe webhook handler.
    """
    db.table(_TABLE).upsert(
        {
            "user_id": user_id,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "stripe_payment_intent_id": stripe_payment_intent_id,
            "plan_tier": plan_tier,
            "status": status,
            "current_period_end": current_period_end.isoformat() if current_period_end else None,
            "cancel_at_period_end": cancel_at_period_end,
        },
        on_conflict="user_id",
    ).execute()


# ─── access predicates ────────────────────────────────────────────────────────
# entitlement=None means no row exists → free tier, no paid subscription.
# When ENFORCE_ANSWER_QUOTAS is False the quota thresholds are skipped entirely
# so that existing personas (answer_count=0 before backfill) are not locked out.


def can_use_chat(
    entitlement: StripeEntitlement | None,
    answer_count: int = 0,
    is_owner: bool = True,
) -> bool:
    """Text chat: free tier is owner-only preview after 30 answers; paid tiers unrestricted."""
    if entitlement is None or entitlement.plan_tier == "free":
        if not is_owner:
            return False
        if settings.enforce_answer_quotas and answer_count < FREE_QUESTION_LIMIT:
            return False
        return True
    return entitlement.status in _PAID_STATUSES or entitlement.plan_tier == "preservation"


def can_use_voice(
    entitlement: StripeEntitlement | None,
    answer_count: int = 0,
    voice_id: object = _VOICE_ID_NOT_SET,
) -> bool:
    """Voice replies: Creator+ plan required.

    When voice_id is explicitly provided, also enforces the no-stock-voice rule:
    if voice_id is falsy the persona has no clone and voice silently downgrades to text.
    Pass voice_id=None to enforce this (WS and persona-access paths).
    Omit voice_id entirely for plan-capability checks (billing status).
    """
    # Product-integrity: no stock voice fallback. Runs before all billing bypasses including
    # voice_always_on — a missing clone is not a billing question, it's a product invariant.
    if voice_id is not _VOICE_ID_NOT_SET and not voice_id:
        return False
    if settings.voice_always_on:
        return True
    if settings.enforce_answer_quotas and answer_count < VOICE_QUESTION_THRESHOLD:
        return False
    if entitlement is None:
        return False
    return (
        entitlement.plan_tier in ("creator", "legacy", "preservation")
        and entitlement.status in _PAID_STATUSES
    )


def can_use_video(
    entitlement: StripeEntitlement | None,
    answer_count: int = 0,
) -> bool:
    """Video avatar replies: requires ≥90 answers (when enforced), Legacy+ plan."""
    if settings.enforce_answer_quotas and answer_count < VIDEO_QUESTION_THRESHOLD:
        return False
    if entitlement is None:
        return False
    return (
        entitlement.plan_tier in ("legacy", "preservation")
        and entitlement.status in _PAID_STATUSES
    )


def can_add_family_member(
    entitlement: StripeEntitlement | None,
    current_count: int,
) -> AccessDecision:
    """Check whether the persona owner can add another family member."""
    if entitlement is None or entitlement.plan_tier == "free":
        return AccessDecision(allowed=False, reason="Family access requires Creator or higher plan.")
    if entitlement.status not in _PAID_STATUSES:
        return AccessDecision(allowed=False, reason="Subscription is not active.")
    limit = _FAMILY_LIMITS.get(entitlement.plan_tier)
    if limit is not None and current_count >= limit:
        return AccessDecision(
            allowed=False,
            reason=f"Creator plan is limited to {limit} family members.",
        )
    return AccessDecision(allowed=True)


def family_member_limit_for_tier(plan_tier: str) -> int | None:
    """Return the family member limit for a given tier. None = unlimited."""
    return _FAMILY_LIMITS.get(plan_tier, 0)
