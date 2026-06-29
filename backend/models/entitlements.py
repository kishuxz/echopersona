from datetime import datetime
from typing import Literal

from pydantic import BaseModel

PlanTier = Literal["free", "creator", "legacy"]
EntitlementStatus = Literal["active", "trialing", "past_due", "canceled", "unpaid"]


class StripeEntitlement(BaseModel):
    id: str
    user_id: str
    stripe_customer_id: str
    stripe_subscription_id: str | None = None
    plan_tier: PlanTier
    status: EntitlementStatus
    cancel_at_period_end: bool = False
    current_period_end: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EntitlementUpsert(BaseModel):
    user_id: str
    stripe_customer_id: str
    stripe_subscription_id: str | None = None
    plan_tier: PlanTier
    status: EntitlementStatus
    cancel_at_period_end: bool = False
    current_period_end: datetime | None = None


class AccessDecision(BaseModel):
    allowed: bool
    reason: str = ""


class BillingStatusResponse(BaseModel):
    plan_tier: PlanTier
    status: EntitlementStatus | None = None
    can_use_chat: bool
    can_use_voice: bool
    can_use_video: bool
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    preservation_locked: bool = False
    can_use_posthumous_chat: bool = False
