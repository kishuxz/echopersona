"""Stage 3: cross-unit entity resolution and coreference.

Collects all entity mentions (people, places) across every memory_unit for
a persona, then uses Groq to cluster aliases into canonical entries.

Output stored as entity_graph on the personas table:
  [{"canonical": "Grandma Rose", "type": "person", "aliases": ["Grandma", "Rose"],
    "description": "maternal grandmother who lived in Brooklyn"}, ...]
"""
import json
import logging

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.1-8b-instant"

_SYSTEM_PROMPT = """\
You are an entity resolution specialist. Given a list of people and places mentioned \
across a person's memory collection, cluster aliases that refer to the same individual \
or location and produce a canonical entity graph.

Return a JSON object:
{
  "entities": [
    {
      "canonical": "Most complete / formal name",
      "type": "person" or "place",
      "aliases": ["all", "name", "variants", "seen"],
      "description": "one-sentence description based on how they appear in memories"
    }
  ]
}

Rules:
- Merge aliases that clearly refer to the same entity (e.g. "Grandma" + "Grandma Rose" + "Rose").
- Keep distinct entities separate even if names overlap.
- type must be exactly "person" or "place".
- Omit entities with fewer than 2 total mentions unless they are prominent.
- descriptions must only use information visible in the provided aliases — do not invent.\
"""


def _is_429(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _collect_raw_entities(units: list[dict]) -> dict[str, list[str]]:
    """Aggregate entity mentions across all units."""
    people: list[str] = []
    places: list[str] = []
    for u in units:
        ents = u.get("entities") or {}
        people.extend(ents.get("people") or [])
        places.extend(ents.get("places") or [])
    return {"people": people, "places": places}


@retry(
    retry=retry_if_exception(_is_429),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(4),
)
async def _call_groq(raw: dict[str, list[str]]) -> list[dict]:
    user_message = json.dumps(raw, ensure_ascii=False)
    payload = {
        "model": _MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 2048,
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
    data = json.loads(resp.json()["choices"][0]["message"]["content"])
    return data.get("entities") or []


def _coerce_entities(raw: list[dict]) -> list[dict]:
    out = []
    for e in raw:
        etype = e.get("type", "")
        if etype not in ("person", "place"):
            continue
        out.append({
            "canonical": str(e.get("canonical", "")).strip(),
            "type": etype,
            "aliases": list(e.get("aliases") or []),
            "description": str(e.get("description", "")).strip(),
        })
    return out


def _mock_entity_graph(units: list[dict]) -> list[dict]:
    raw = _collect_raw_entities(units)
    seen_people = list({p for p in raw["people"] if p})
    seen_places = list({p for p in raw["places"] if p})
    graph = []
    for name in seen_people[:10]:
        graph.append({"canonical": name, "type": "person", "aliases": [name], "description": ""})
    for name in seen_places[:5]:
        graph.append({"canonical": name, "type": "place", "aliases": [name], "description": ""})
    return graph


async def build_entity_graph(units: list[dict]) -> list[dict]:
    """Resolve entities across all memory units and return the entity graph.

    Falls back to a simple dedup-only list on any error.
    """
    if not units:
        return []

    if settings.mock_mode:
        return _mock_entity_graph(units)

    raw = _collect_raw_entities(units)
    if not raw["people"] and not raw["places"]:
        logger.info("[Stage3] no entity mentions found in units")
        return []

    try:
        entities = await _call_groq(raw)
        entities = _coerce_entities(entities)
        logger.info("[Stage3] resolved %d entities", len(entities))
        return entities
    except Exception as exc:
        logger.warning("[Stage3] entity resolution failed (%s), using simple dedup", exc)
        return _mock_entity_graph(units)
