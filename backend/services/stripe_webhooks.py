from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import stripe

from config import settings
from services.entitlements import (
    get_entitlement_by_customer_or_subscription,
    get_entitlement_for_user,
    upsert_entitlement_from_subscription,
)

if TYPE_CHECKING:
    from supabase import Client

stripe.api_key = settings.stripe_secret_key

logger = logging.getLogger(__name__)

_EVENTS_TABLE = "stripe_webhook_events"
_PRESERVATION_LOCKS_TABLE = "preservation_locks"

_STRIPE_STATUS_MAP: dict[str, str] = {
    "active": "active",
    "trialing": "trialing",
    "past_due": "past_due",
    "canceled": "canceled",
    "unpaid": "unpaid",
}


def _price_to_tier(price_id: str) -> str | None:
    """Map a Stripe price ID to a plan tier. Returns None for unrecognised IDs."""
    if not price_id:
        return None
    creator = settings.stripe_price_creator_monthly
    legacy = settings.stripe_price_legacy_monthly
    preservation = settings.stripe_price_preservation_onetime
    if creator and price_id == creator:
        return "creator"
    if legacy and price_id == legacy:
        return "legacy"
    if preservation and price_id == preservation:
        return "preservation"
    return None


async def record_event_idempotent(db: "Client", event_id: str, event_type: str) -> bool:
    """Record event_id in stripe_webhook_events before processing.

    Returns True  → event is new; proceed with processing.
    Returns False → event already recorded; skip (return 200 to Stripe).
    """
    existing = (
        db.table(_EVENTS_TABLE)
        .select("stripe_event_id")
        .eq("stripe_event_id", event_id)
        .maybe_single()
        .execute()
    )
    if existing.data:
        return False
    db.table(_EVENTS_TABLE).insert(
        {"stripe_event_id": event_id, "event_type": event_type}
    ).execute()
    return True


async def _resolve_user_id(db: "Client", subscription) -> str | None:
    """Resolve Supabase user_id from subscription metadata, then DB lookup."""
    metadata = getattr(subscription, "metadata", {}) or {}
    user_id = metadata.get("supabase_user_id")
    if user_id:
        return str(user_id)

    customer_id = str(subscription.customer) if getattr(subscription, "customer", None) else None
    sub_id = subscription.id if getattr(subscription, "id", None) else None

    existing = await get_entitlement_by_customer_or_subscription(
        db,
        stripe_customer_id=customer_id,
        stripe_subscription_id=sub_id,
    )
    return existing.user_id if existing else None


async def _upsert_from_subscription(
    db: "Client",
    subscription,
    user_id: str,
) -> None:
    """Extract fields from a Stripe Subscription object and upsert the entitlement row."""
    price_id = ""
    try:
        price_id = subscription.items.data[0].price.id
    except (AttributeError, IndexError, TypeError):
        pass

    plan_tier = _price_to_tier(price_id)
    if plan_tier is None:
        logger.warning(
            "stripe_webhooks: unknown price_id '%s' on subscription %s — skipping upsert",
            price_id,
            getattr(subscription, "id", "?"),
        )
        return

    raw_status = getattr(subscription, "status", "canceled")
    status = _STRIPE_STATUS_MAP.get(raw_status, "canceled")

    period_end_ts = getattr(subscription, "current_period_end", None)
    current_period_end = (
        datetime.fromtimestamp(period_end_ts, tz=timezone.utc) if period_end_ts else None
    )

    await upsert_entitlement_from_subscription(
        db,
        user_id=user_id,
        stripe_customer_id=str(subscription.customer),
        stripe_subscription_id=subscription.id,
        plan_tier=plan_tier,
        status=status,
        current_period_end=current_period_end,
        cancel_at_period_end=bool(getattr(subscription, "cancel_at_period_end", False)),
    )


async def handle_checkout_completed(db: "Client", session) -> None:
    """Handle checkout.session.completed.

    Branches on session.mode: 'payment' routes to the Preservation handler;
    'subscription' routes to the standard subscription handler.
    """
    mode = getattr(session, "mode", "subscription")

    if mode == "payment":
        await handle_preservation_checkout(db, session)
        return

    subscription_id = getattr(session, "subscription", None)
    if not subscription_id:
        logger.info("stripe_webhooks: checkout.session.completed has no subscription — skipping")
        return

    subscription = stripe.Subscription.retrieve(subscription_id)

    metadata = getattr(session, "metadata", {}) or {}
    user_id: str | None = metadata.get("supabase_user_id")
    if not user_id:
        user_id = await _resolve_user_id(db, subscription)

    if not user_id:
        logger.warning("stripe_webhooks: cannot resolve user_id from checkout session — skipping")
        return

    await _upsert_from_subscription(db, subscription, user_id)


async def handle_preservation_checkout(db: "Client", session) -> None:
    """Handle a completed Preservation one-time payment checkout.

    Upserts the entitlement row with plan_tier='preservation' and writes
    a preservation_locks row so the persona is never deleted.
    """
    metadata = getattr(session, "metadata", {}) or {}
    user_id: str | None = metadata.get("supabase_user_id")
    persona_id: str | None = metadata.get("persona_id")
    payment_intent_id = getattr(session, "payment_intent", None)

    if not user_id:
        logger.warning("stripe_webhooks: preservation checkout missing supabase_user_id — skipping")
        return
    if not payment_intent_id:
        logger.warning("stripe_webhooks: preservation checkout missing payment_intent — skipping")
        return

    # Resolve the tier the subject held before purchasing Preservation.
    existing = await get_entitlement_for_user(db, user_id)
    tier_at_lock = existing.plan_tier if existing and existing.plan_tier != "preservation" else "free"
    customer_id = str(getattr(session, "customer", "")) or (
        existing.stripe_customer_id if existing else ""
    )

    await upsert_entitlement_from_subscription(
        db,
        user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=None,
        plan_tier="preservation",
        status="active",
        current_period_end=None,
        cancel_at_period_end=False,
        stripe_payment_intent_id=str(payment_intent_id),
    )

    if persona_id:
        try:
            db.table(_PRESERVATION_LOCKS_TABLE).upsert(
                {
                    "persona_id": persona_id,
                    "user_id": user_id,
                    "stripe_payment_intent_id": str(payment_intent_id),
                    "tier_at_lock": tier_at_lock,
                },
                on_conflict="persona_id",
            ).execute()
        except Exception:
            logger.warning(
                "stripe_webhooks: failed to write preservation_locks row for persona %s", persona_id
            )

    logger.info(
        "stripe_webhooks: preservation lock applied — user=%s persona=%s", user_id, persona_id
    )


async def handle_subscription_event(db: "Client", subscription) -> None:
    """Handle customer.subscription.{created,updated,deleted}."""
    user_id = await _resolve_user_id(db, subscription)
    if not user_id:
        logger.warning(
            "stripe_webhooks: cannot resolve user_id for subscription %s — skipping",
            getattr(subscription, "id", "?"),
        )
        return
    await _upsert_from_subscription(db, subscription, user_id)


async def process_stripe_event(db: "Client", event) -> None:
    """Route a verified Stripe event to the appropriate handler."""
    event_type: str = event.type
    obj = event.data.object

    if event_type == "checkout.session.completed":
        await handle_checkout_completed(db, obj)
    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        await handle_subscription_event(db, obj)
    else:
        logger.debug("stripe_webhooks: unhandled event type '%s'", event_type)
