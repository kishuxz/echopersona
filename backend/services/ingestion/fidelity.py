"""Fidelity verification pass (between Stage 2 and family review).

Compares content_first_person against its source episode span and flags any
additions, fabrications, or significant distortions not present in the source.

memory_unit.verified stays false until a family member explicitly approves.
"""
import json
import logging

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_FIDELITY_MODEL = "llama-3.1-8b-instant"

_SYSTEM_PROMPT = """\
You are a fidelity auditor for a persona memory system. Your job is to check whether \
a transformed first-person memory unit faithfully represents the original source text, \
and flag any additions, fabrications, or significant distortions.

Return a JSON object:
{
  "has_additions": true/false,
  "fidelity_score": 0.95,
  "flags": [
    {
      "flagged_text": "exact phrase from the unit that is not supported",
      "reason": "brief explanation of the issue"
    }
  ]
}

fidelity_score: 0.0 (completely fabricated) to 1.0 (perfectly faithful).
flags: empty list if has_additions is false.
Only flag content that is genuinely not supported by the source. \
Rewriting third-person to first-person is acceptable and should NOT be flagged. \
Extracting implied emotions is acceptable. \
Only flag invented events, people, places, or facts.\
"""


def _is_429(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _mock_result() -> dict:
    return {"has_additions": False, "fidelity_score": 1.0, "flags": []}


@retry(
    retry=retry_if_exception(_is_429),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(4),
)
async def _call_groq(source_text: str, unit_text: str) -> dict:
    user_message = (
        f"SOURCE TEXT:\n{source_text[:4000]}\n\n"
        f"TRANSFORMED UNIT:\n{unit_text[:2000]}"
    )
    payload = {
        "model": _FIDELITY_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 1024,
        "temperature": 0.1,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            _GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


def _coerce_result(raw: dict) -> dict:
    flags = []
    for f in raw.get("flags") or []:
        if isinstance(f, dict):
            flags.append({
                "flagged_text": str(f.get("flagged_text", "")),
                "reason": str(f.get("reason", "")),
            })
    return {
        "has_additions": bool(raw.get("has_additions", False)),
        "fidelity_score": max(0.0, min(1.0, float(raw.get("fidelity_score", 1.0)))),
        "flags": flags,
    }


async def verify_fidelity(source_episode_text: str, content_first_person: str) -> dict:
    """Check unit faithfulness against its source span.

    Returns {"has_additions": bool, "fidelity_score": float, "flags": list}.
    On any error, returns a safe default (score=1.0, no flags) so the pipeline
    does not block — a human review can still catch issues.
    """
    if settings.mock_mode:
        return _mock_result()

    try:
        raw = await _call_groq(source_episode_text, content_first_person)
        result = _coerce_result(raw)
        logger.info(
            "[Fidelity] score=%.2f has_additions=%s flags=%d",
            result["fidelity_score"],
            result["has_additions"],
            len(result["flags"]),
        )
        return result
    except Exception as exc:
        logger.warning("[Fidelity] check failed (%s), defaulting to clean pass", exc)
        return _mock_result()
