from __future__ import annotations

from typing import TYPE_CHECKING

import stripe

from config import settings
from services.entitlements import get_entitlement_for_user

if TYPE_CHECKING:
    from supabase import Client

stripe.api_key = settings.stripe_secret_key


async def create_checkout_session(
    db: "Client",
    user_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    mode: str = "subscription",
    extra_metadata: dict | None = None,
) -> dict:
    """Get or create a Stripe customer for user_id, then create a Checkout Session.
    Reuses stripe_customer_id from an existing entitlement row to avoid duplicate customers.
    Returns {"checkout_url": str, "session_id": str}.
    """
    existing = await get_entitlement_for_user(db, user_id)
    if existing and existing.stripe_customer_id:
        customer_id = existing.stripe_customer_id
    else:
        customer = stripe.Customer.create(metadata={"supabase_user_id": user_id})
        customer_id = customer.id

    metadata: dict = {"supabase_user_id": user_id}
    if extra_metadata:
        metadata.update(extra_metadata)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        mode=mode,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
    )

    return {"checkout_url": session.url, "session_id": session.id}
