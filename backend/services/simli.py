import httpx
import logging
from config import settings

logger = logging.getLogger(__name__)

SIMLI_TOKEN_URL = "https://api.simli.ai/compose/token"


async def create_session(face_id: str) -> str | None:
    """
    POST to Simli /compose/token and return the session_token.
    Returns None if SIMLI_API_KEY is absent or the request fails.
    """
    if not settings.simli_api_key:
        logger.debug("[SIMLI] SIMLI_API_KEY not configured — skipping")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                SIMLI_TOKEN_URL,
                headers={"x-simli-api-key": settings.simli_api_key},
                json={
                    "faceId": face_id,
                    "apiVersion": "v2",
                    "audioInputFormat": "pcm16",
                    "handleSilence": True,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("session_token") or data.get("sessionToken")
            if not token:
                logger.error("[SIMLI] no session_token in response: %s", data)
                return None
            logger.info("[SIMLI] session created for face %s", face_id)
            return token
    except httpx.HTTPStatusError as e:
        logger.error("[SIMLI] token request failed: %s %s", e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.error("[SIMLI] error: %s", e)
        return None
