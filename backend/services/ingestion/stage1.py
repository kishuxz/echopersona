"""Stage 1: episode segmentation.

Splits raw_text from a source into episodic memory units at natural story
boundaries. Each episode is a self-contained memory linked back to its
character-offset span in the original text.
"""
import json
import logging

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_SEGMENT_MODEL = "llama-3.1-8b-instant"

_SYSTEM_PROMPT = """\
You are a memory segmentation specialist. Given raw text from recorded memories \
(transcription, diary entry, letter, etc.), split it into distinct episodic units. \
Each unit should be one coherent, self-contained memory or story.

Return a JSON object: {"episodes": [{"episode_text": "...", "span_start": 0, "span_end": 100}]}

Rules:
- span_start/span_end are character offsets into the original text (0-indexed).
- Each episode should be 50-600 words.
- Preserve the original wording exactly in episode_text.
- If the text is already one coherent memory, return it as a single episode.
- Never fabricate or paraphrase — only split, never rewrite.\
"""


def _is_429(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _mock_episodes(raw_text: str) -> list[dict]:
    return [{"episode_text": raw_text.strip(), "span_start": 0, "span_end": len(raw_text)}]


@retry(
    retry=retry_if_exception(_is_429),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(4),
)
async def _call_groq(raw_text: str) -> list[dict]:
    payload = {
        "model": _SEGMENT_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": raw_text[:12000]},  # guard against giant inputs
        ],
        "max_tokens": 4096,
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

    content = resp.json()["choices"][0]["message"]["content"]
    data = json.loads(content)
    episodes = data.get("episodes", [])
    if not isinstance(episodes, list):
        raise ValueError("Groq returned non-list episodes")
    return episodes


def _validate_episodes(episodes: list[dict], raw_text: str) -> list[dict]:
    """Clamp spans to valid range and drop empty episodes."""
    valid = []
    for ep in episodes:
        text = (ep.get("episode_text") or "").strip()
        if not text:
            continue
        start = max(0, int(ep.get("span_start", 0)))
        end = min(len(raw_text), int(ep.get("span_end", len(raw_text))))
        if end <= start:
            end = min(start + len(text), len(raw_text))
        valid.append({"episode_text": text, "span_start": start, "span_end": end})
    return valid


async def segment_episodes(raw_text: str) -> list[dict]:
    """Split raw_text into episodic units.

    Returns list of {"episode_text": str, "span_start": int, "span_end": int}.
    Falls back to a single episode if segmentation fails.
    """
    if not raw_text.strip():
        return []

    if settings.mock_mode:
        logger.info("[Stage1] mock mode — returning single episode")
        return _mock_episodes(raw_text)

    try:
        episodes = await _call_groq(raw_text)
        episodes = _validate_episodes(episodes, raw_text)
        if not episodes:
            raise ValueError("No valid episodes after validation")
        logger.info("[Stage1] segmented %d episodes from %d chars", len(episodes), len(raw_text))
        return episodes
    except Exception as exc:
        logger.warning("[Stage1] segmentation failed (%s), falling back to single episode", exc)
        return _mock_episodes(raw_text)
