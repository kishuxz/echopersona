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
from services.preservation import (
    get_posthumous_subscription_by_stripe_id,
    upsert_posthumous_subscription,
    upsert_preservation,
)

if TYPE_CHECKING:
    from supabase import Client

stripe.api_key = settings.stripe_secret_key

logger = logging.getLogger(__name__)

_EVENTS_TABLE = "stripe_webhook_events"

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


async def handle_preservation_checkout(db: "Client", session) -> None:
    """Handle checkout.session.completed where mode=payment (preservation purchase)."""
    metadata = getattr(session, "metadata", {}) or {}
    user_id: str | None = metadata.get("supabase_user_id")
    persona_id: str | None = metadata.get("persona_id")

    if not user_id or not persona_id:
        logger.warning(
            "stripe_webhooks: preservation checkout missing user_id or persona_id — skipping"
        )
        return

    payment_intent_id = getattr(session, "payment_intent", None)
    if payment_intent_id:
        payment_intent_id = str(payment_intent_id)

    customer_id = str(session.customer) if getattr(session, "customer", None) else ""
    session_id_str = str(session.id) if getattr(session, "id", None) else None

    await upsert_preservation(
        db,
        persona_id=persona_id,
        subject_user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_payment_intent_id=payment_intent_id,
        stripe_checkout_session_id=session_id_str,
    )
    logger.info(
        "stripe_webhooks: preservation purchased for persona %s by user %s",
        persona_id,
        user_id,
    )


async def handle_preservation_payment_intent(db: "Client", payment_intent) -> None:
    """Belt-and-suspenders: payment_intent.succeeded for preservation purchases.
    Only acts when metadata.purchase_type == 'preservation'; silently skips all others.
    """
    metadata = getattr(payment_intent, "metadata", {}) or {}
    if metadata.get("purchase_type") != "preservation":
        return

    user_id: str | None = metadata.get("supabase_user_id")
    persona_id: str | None = metadata.get("persona_id")

    if not user_id or not persona_id:
        logger.warning(
            "stripe_webhooks: preservation payment_intent missing metadata — skipping"
        )
        return

    customer_id = str(payment_intent.customer) if getattr(payment_intent, "customer", None) else ""
    pi_id = str(payment_intent.id) if getattr(payment_intent, "id", None) else None

    await upsert_preservation(
        db,
        persona_id=persona_id,
        subject_user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_payment_intent_id=pi_id,
        stripe_checkout_session_id=None,
    )
    logger.info(
        "stripe_webhooks: preservation confirmed via payment_intent for persona %s",
        persona_id,
    )


async def handle_posthumous_checkout(db: "Client", session) -> None:
    """Handle checkout.session.completed where purchase_type=posthumous_access."""
    metadata = getattr(session, "metadata", {}) or {}
    subscriber_user_id: str | None = metadata.get("supabase_user_id")
    persona_id: str | None = metadata.get("persona_id")

    if not subscriber_user_id or not persona_id:
        logger.warning(
            "stripe_webhooks: posthumous checkout missing user_id or persona_id — skipping"
        )
        return

    subscription_id = getattr(session, "subscription", None)
    if not subscription_id:
        logger.warning("stripe_webhooks: posthumous checkout has no subscription — skipping")
        return

    subscription = stripe.Subscription.retrieve(subscription_id)
    customer_id = str(subscription.customer) if getattr(subscription, "customer", None) else ""

    raw_status = getattr(subscription, "status", "active")
    status = _STRIPE_STATUS_MAP.get(raw_status, "active")

    period_end_ts = getattr(subscription, "current_period_end", None)
    current_period_end = (
        datetime.fromtimestamp(period_end_ts, tz=timezone.utc) if period_end_ts else None
    )

    await upsert_posthumous_subscription(
        db,
        persona_id=persona_id,
        subscriber_user_id=subscriber_user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription.id,
        status=status,
        current_period_end=current_period_end,
        cancel_at_period_end=bool(getattr(subscription, "cancel_at_period_end", False)),
    )
    logger.info(
        "stripe_webhooks: posthumous subscription activated for persona %s by user %s",
        persona_id,
        subscriber_user_id,
    )


async def handle_posthumous_subscription_event(
    db: "Client", subscription, event_type: str
) -> None:
    """Handle customer.subscription.{created,updated,deleted} for posthumous access."""
    metadata = getattr(subscription, "metadata", {}) or {}
    subscriber_user_id: str | None = metadata.get("supabase_user_id")
    persona_id: str | None = metadata.get("persona_id")

    # Fallback: look up by subscription ID when metadata is absent
    if not subscriber_user_id or not persona_id:
        sub_id = getattr(subscription, "id", None)
        if sub_id:
            existing = await get_posthumous_subscription_by_stripe_id(db, sub_id)
            if existing:
                subscriber_user_id = existing.subscriber_user_id
                persona_id = existing.persona_id

    if not subscriber_user_id or not persona_id:
        logger.warning(
            "stripe_webhooks: posthumous subscription event cannot resolve persona/user — skipping"
        )
        return

    customer_id = str(subscription.customer) if getattr(subscription, "customer", None) else ""

    if event_type == "customer.subscription.deleted":
        status = "canceled"
    else:
        raw_status = getattr(subscription, "status", "active")
        status = _STRIPE_STATUS_MAP.get(raw_status, "active")

    period_end_ts = getattr(subscription, "current_period_end", None)
    current_period_end = (
        datetime.fromtimestamp(period_end_ts, tz=timezone.utc) if period_end_ts else None
    )

    await upsert_posthumous_subscription(
        db,
        persona_id=persona_id,
        subscriber_user_id=subscriber_user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription.id,
        status=status,
        current_period_end=current_period_end,
        cancel_at_period_end=bool(getattr(subscription, "cancel_at_period_end", False)),
    )


async def handle_checkout_completed(db: "Client", session) -> None:
    """Handle checkout.session.completed for standard subscription checkouts.

    Only handles mode=subscription. mode=payment is routed to
    handle_preservation_checkout by process_stripe_event before this is called.
    """
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
        mode = getattr(obj, "mode", "subscription")
        if mode == "payment":
            await handle_preservation_checkout(db, obj)
        else:
            metadata = getattr(obj, "metadata", {}) or {}
            if metadata.get("purchase_type") == "posthumous_access":
                await handle_posthumous_checkout(db, obj)
            else:
                await handle_checkout_completed(db, obj)
    elif event_type == "payment_intent.succeeded":
        await handle_preservation_payment_intent(db, obj)
    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        metadata = getattr(obj, "metadata", {}) or {}
        if metadata.get("purchase_type") == "posthumous_access":
            await handle_posthumous_subscription_event(db, obj, event_type)
        else:
            await handle_subscription_event(db, obj)
    else:
        logger.debug("stripe_webhooks: unhandled event type '%s'", event_type)
