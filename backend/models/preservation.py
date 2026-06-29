from datetime import datetime
from typing import Literal

from pydantic import BaseModel

PreservationStatus = Literal["paid", "refunded"]
PosthumousStatus = Literal["active", "trialing", "past_due", "canceled", "unpaid"]


class PersonaPreservation(BaseModel):
    id: str
    persona_id: str
    subject_user_id: str
    stripe_customer_id: str
    stripe_payment_intent_id: str | None = None
    stripe_checkout_session_id: str | None = None
    status: PreservationStatus
    paid_at: datetime | None = None
    created_at: datetime | None = None


class PosthumousAccessSubscription(BaseModel):
    id: str
    persona_id: str
    subscriber_user_id: str
    stripe_customer_id: str
    stripe_subscription_id: str | None = None
    status: PosthumousStatus
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
