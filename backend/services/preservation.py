from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from models.preservation import PersonaPreservation, PosthumousAccessSubscription

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)

_PRESERVATION_TABLE = "persona_preservation"
_POSTHUMOUS_TABLE = "posthumous_access_subscriptions"

_ACTIVE_POSTHUMOUS: frozenset[str] = frozenset({"active", "trialing"})


# ─── persona_preservation queries ────────────────────────────────────────────

async def get_preservation_for_persona(
    db: "Client", persona_id: str
) -> PersonaPreservation | None:
    result = (
        db.table(_PRESERVATION_TABLE)
        .select("*")
        .eq("persona_id", persona_id)
        .maybe_single()
        .execute()
    )
    if result is None or not result.data:
        return None
    return PersonaPreservation(**result.data)


async def upsert_preservation(
    db: "Client",
    persona_id: str,
    subject_user_id: str,
    stripe_customer_id: str,
    stripe_payment_intent_id: str | None,
    stripe_checkout_session_id: str | None,
) -> None:
    """Record a successful preservation purchase. Idempotent on persona_id."""
    db.table(_PRESERVATION_TABLE).upsert(
        {
            "persona_id": persona_id,
            "subject_user_id": subject_user_id,
            "stripe_customer_id": stripe_customer_id,
            "stripe_payment_intent_id": stripe_payment_intent_id,
            "stripe_checkout_session_id": stripe_checkout_session_id,
            "status": "paid",
        },
        on_conflict="persona_id",
    ).execute()


# ─── posthumous_access_subscriptions queries ──────────────────────────────────

async def get_posthumous_subscription(
    db: "Client",
    persona_id: str,
    subscriber_user_id: str,
) -> PosthumousAccessSubscription | None:
    result = (
        db.table(_POSTHUMOUS_TABLE)
        .select("*")
        .eq("persona_id", persona_id)
        .eq("subscriber_user_id", subscriber_user_id)
        .maybe_single()
        .execute()
    )
    if result is None or not result.data:
        return None
    return PosthumousAccessSubscription(**result.data)


async def get_posthumous_subscription_by_stripe_id(
    db: "Client",
    stripe_subscription_id: str,
) -> PosthumousAccessSubscription | None:
    result = (
        db.table(_POSTHUMOUS_TABLE)
        .select("*")
        .eq("stripe_subscription_id", stripe_subscription_id)
        .maybe_single()
        .execute()
    )
    if result is None or not result.data:
        return None
    return PosthumousAccessSubscription(**result.data)


async def upsert_posthumous_subscription(
    db: "Client",
    persona_id: str,
    subscriber_user_id: str,
    stripe_customer_id: str,
    stripe_subscription_id: str | None,
    status: str,
    current_period_end: datetime | None,
    cancel_at_period_end: bool = False,
) -> None:
    db.table(_POSTHUMOUS_TABLE).upsert(
        {
            "persona_id": persona_id,
            "subscriber_user_id": subscriber_user_id,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "status": status,
            "current_period_end": current_period_end.isoformat() if current_period_end else None,
            "cancel_at_period_end": cancel_at_period_end,
        },
        on_conflict="persona_id,subscriber_user_id",
    ).execute()


# ─── access predicates ────────────────────────────────────────────────────────

def can_access_preserved_persona(preservation: PersonaPreservation | None) -> bool:
    """True iff this persona has a paid preservation purchase (data is storage-locked)."""
    return preservation is not None and preservation.status == "paid"


def can_access_posthumous(subscription: PosthumousAccessSubscription | None) -> bool:
    """True iff the calling listener holds an active posthumous access subscription."""
    if subscription is None:
        return False
    return subscription.status in _ACTIVE_POSTHUMOUS
