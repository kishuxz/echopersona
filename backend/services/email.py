"""Thin async wrapper around the Resend email REST API.

All functions return bool — True = sent, False = failed.
Failures are logged at WARNING and never re-raised (email is always best-effort).
When RESEND_API_KEY is absent the send is skipped and logged; the caller never errors.
"""
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


async def _send(payload: dict) -> bool:
    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not set — email skipped: %s", payload.get("subject"))
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                _RESEND_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
            )
            r.raise_for_status()
            return True
    except Exception as exc:
        logger.warning("email send failed (%s): %s", payload.get("subject"), exc)
        return False


async def send_invite_email(
    to_email: str,
    inviter_name: str,
    persona_name: str,
    token: str,
) -> bool:
    invite_link = f"{settings.public_base_url}/invite/accept?token={token}"
    body = (
        f"{inviter_name} has invited you to connect with their EchoPersona — "
        f"an AI twin of {persona_name} built from their own stories, memories, and voice.\n\n"
        f"Click the link below to accept:\n{invite_link}\n\n"
        f"This link expires in 7 days. If you weren't expecting this, you can safely ignore it.\n\n"
        f"— The EchoPersona team"
    )
    return await _send({
        "from": settings.resend_from_address,
        "to": [to_email],
        "subject": f"{persona_name}'s EchoPersona — you're invited",
        "text": body,
    })


async def send_readiness_notification(
    to_email: str,
    persona_name: str,
    persona_id: str,
) -> bool:
    chat_link = f"{settings.public_base_url}/persona/{persona_id}/chat"
    body = (
        f"Good news — {persona_name}'s EchoPersona is now ready for conversation.\n\n"
        f"Start talking here:\n{chat_link}\n\n"
        f"— The EchoPersona team"
    )
    return await _send({
        "from": settings.resend_from_address,
        "to": [to_email],
        "subject": f"{persona_name}'s EchoPersona is ready to talk",
        "text": body,
    })


async def send_acceptance_confirmation(
    to_email: str,
    persona_name: str,
    member_email: str,
) -> bool:
    body = (
        f"{member_email} has accepted your invitation and is now connected to {persona_name}.\n\n"
        f"— The EchoPersona team"
    )
    return await _send({
        "from": settings.resend_from_address,
        "to": [to_email],
        "subject": f"{member_email} joined your EchoPersona",
        "text": body,
    })
