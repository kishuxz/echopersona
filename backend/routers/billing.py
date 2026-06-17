import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import settings
from middleware.auth import get_current_user
from services.billing import create_checkout_session
from services.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

# Maps plan_tier values to config attribute names — price IDs never come from the client.
_PLAN_PRICE_MAP: dict[str, str] = {
    "creator": "stripe_price_creator_monthly",
    "legacy": "stripe_price_legacy_monthly",
}


class CheckoutRequest(BaseModel):
    plan_tier: Literal["creator", "legacy"]


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


@router.post("/checkout", response_model=CheckoutResponse)
async def start_checkout(
    body: CheckoutRequest,
    user_id: str = Depends(get_current_user),
) -> CheckoutResponse:
    price_id: str = getattr(settings, _PLAN_PRICE_MAP[body.plan_tier], "")
    if not price_id:
        raise HTTPException(
            status_code=500,
            detail=f"Stripe price ID for plan '{body.plan_tier}' is not configured.",
        )

    db = get_db()
    result = await create_checkout_session(
        db=db,
        user_id=user_id,
        price_id=price_id,
        success_url=settings.frontend_billing_success_url,
        cancel_url=settings.frontend_billing_cancel_url,
    )
    return CheckoutResponse(checkout_url=result["checkout_url"], session_id=result["session_id"])
