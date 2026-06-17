from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from models.entitlements import StripeEntitlement

if TYPE_CHECKING:
    from supabase import Client

_TABLE = "stripe_entitlements"
_PAID_STATUSES: frozenset[str] = frozenset({"active", "trialing"})

FREE_QUESTION_LIMIT: int = 20


async def get_entitlement_for_user(db: "Client", user_id: str) -> StripeEntitlement | None:
    """Return the entitlement row for user_id, or None (= free tier with no subscription)."""
    result = (
        db.table(_TABLE)
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        return None
    return StripeEntitlement(**result.data)


async def get_entitlement_by_customer_or_subscription(
    db: "Client",
    stripe_customer_id: str | None,
    stripe_subscription_id: str | None,
) -> StripeEntitlement | None:
    """Find an entitlement by Stripe customer ID, falling back to subscription ID.
    Used by the webhook handler to resolve which user an event belongs to.
    """
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
) -> None:
    """Create or update the entitlement row for user_id.
    Conflict resolution is on user_id (UNIQUE constraint on the table).
    Called exclusively by the Stripe webhook handler.
    """
    db.table(_TABLE).upsert(
        {
            "user_id": user_id,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "plan_tier": plan_tier,
            "status": status,
            "current_period_end": current_period_end.isoformat() if current_period_end else None,
            "cancel_at_period_end": cancel_at_period_end,
        },
        on_conflict="user_id",
    ).execute()


# ─── access predicates ────────────────────────────────────────────────────────
# entitlement=None means no row exists → free tier, no paid subscription.


def can_use_chat(entitlement: StripeEntitlement | None) -> bool:
    """Text chat is available on all tiers including free."""
    return True


def can_use_voice(entitlement: StripeEntitlement | None) -> bool:
    """Voice replies require Creator or Legacy on an active/trialing subscription."""
    if entitlement is None:
        return False
    return entitlement.plan_tier in ("creator", "legacy") and entitlement.status in _PAID_STATUSES


def can_use_video(entitlement: StripeEntitlement | None) -> bool:
    """Video avatar replies require Legacy on an active/trialing subscription."""
    if entitlement is None:
        return False
    return entitlement.plan_tier == "legacy" and entitlement.status in _PAID_STATUSES
