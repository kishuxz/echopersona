"""Stage 4: style exemplar bank.

Extracts 5-8 characteristic speech excerpts from the persona's memory units
(preferring audio/video transcripts, which preserve natural spoken voice).

These exemplars are stored on the persona record and injected into the system
prompt to help the LLM mimic authentic phrasing and cadence.
"""
import json
import logging

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.1-8b-instant"
_TARGET_EXEMPLARS = 6

_SYSTEM_PROMPT = """\
You are a speech style analyst. Given a collection of first-person memory texts \
written or spoken by one person, extract short excerpts (1-3 sentences each) that \
best capture their characteristic voice, phrasing, vocabulary, and sentence rhythm.

Return a JSON object:
{
  "exemplars": [
    "Exact quote or close paraphrase of a characteristic phrase or passage.",
    ...
  ]
}

Rules:
- Extract 5-8 exemplars total.
- Each exemplar must be a verbatim or near-verbatim excerpt from the provided texts.
- Choose excerpts that show distinctive vocabulary, idioms, emotional openness, or sentence structure.
- Prefer spoken/conversational passages over formal writing.
- Do NOT invent or paraphrase beyond light punctuation fixes.\
"""


def _is_429(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _select_source_units(units: list[dict]) -> list[dict]:
    """Prioritise audio/video units (they capture real spoken voice)."""
    spoken: list[dict] = []
    written: list[dict] = []
    for u in units:
        src = u.get("source") or {}
        modality = (src.get("modality") or "").lower()
        if modality in ("audio", "video"):
            spoken.append(u)
        else:
            written.append(u)
    # Use up to 10 spoken + 5 written to stay within token limits
    return (spoken[:10] + written[:5])


def _build_corpus(units: list[dict]) -> str:
    parts = []
    for i, u in enumerate(units, 1):
        text = (u.get("content_first_person") or "").strip()
        if text:
            parts.append(f"[{i}] {text}")
    return "\n\n".join(parts)


@retry(
    retry=retry_if_exception(_is_429),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(4),
)
async def _call_groq(corpus: str) -> list[str]:
    payload = {
        "model": _MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": corpus[:10000]},  # guard token limit
        ],
        "max_tokens": 1024,
        "temperature": 0.3,
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
    data = json.loads(resp.json()["choices"][0]["message"]["content"])
    return [str(e).strip() for e in (data.get("exemplars") or []) if e]


def _mock_exemplars(units: list[dict]) -> list[str]:
    selected = _select_source_units(units)[:_TARGET_EXEMPLARS]
    return [
        (u.get("content_first_person") or "")[:150].strip()
        for u in selected
        if u.get("content_first_person")
    ]


async def extract_style_exemplars(units: list[dict]) -> list[str]:
    """Return a list of characteristic speech excerpts for the persona.

    Falls back to first-sentence snippets on any error.
    """
    if not units:
        return []

    if settings.mock_mode:
        return _mock_exemplars(units)

    source_units = _select_source_units(units)
    if not source_units:
        logger.info("[Stage4] no suitable source units for style extraction")
        return []

    corpus = _build_corpus(source_units)
    try:
        exemplars = await _call_groq(corpus)
        exemplars = exemplars[:_TARGET_EXEMPLARS]
        logger.info("[Stage4] extracted %d style exemplars", len(exemplars))
        return exemplars
    except Exception as exc:
        logger.warning("[Stage4] style extraction failed (%s), using fallback snippets", exc)
        return _mock_exemplars(units)
