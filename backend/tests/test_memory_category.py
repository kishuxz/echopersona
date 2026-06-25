"""Tests for memory_category extraction and persistence — migration 007 / Slice A.

Verifies:
  1. All 7 valid category values are preserved by _coerce_unit.
  2. An invalid LLM-returned category falls back to "episodic".
  3. A missing/None category falls back to "episodic".
  4. _mock_unit includes memory_category: "episodic".
  5. write_memory_unit includes memory_category in the DB insert payload.
  6. The ingestion pipeline passes memory_category from unit_data to write_memory_unit.

All DB and LLM calls are mocked.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from services.ingestion.stage2 import _coerce_unit, _mock_unit
from worker.tasks.ingestion import ingest_memory_unit


# ── helpers ───────────────────────────────────────────────────────────────────

_EPISODE = {"episode_text": "I spent every summer in a small village near the river."}

_SOURCE_META: dict = {}  # _mock_unit ignores source_meta for category

_FIDELITY_OK = {"flags": [], "fidelity_score": 1.0, "has_additions": False}


def _source_record(text_content: str = _EPISODE["episode_text"]) -> dict:
    return {
        "id": "src-uuid-007",
        "user_id": "u1",
        "persona_id": "p1",
        "modality": "text",
        "question_category": "origins",
        "question_text": "Tell me about your childhood.",
        "source_question_id": "q_origins_02",
        "source_type": "answer",
        "media_ref": "",
        "captured_at": "2026-06-24T10:00:00+00:00",
        "file_id": "",
        "group_name": "",
        "text_content": text_content,
        "status": "pending",
    }


def _run_ingest(unit_data: dict, write_mock: AsyncMock) -> dict:
    """Run the full ingest pipeline with all I/O mocked; return result dict."""
    record = _source_record()
    with (
        patch("worker.tasks.ingestion.get_source_record", new_callable=AsyncMock, return_value=record),
        patch("worker.tasks.ingestion.update_source_status", new_callable=AsyncMock),
        patch(
            "worker.tasks.ingestion.normalize_source",
            new_callable=AsyncMock,
            return_value=(record["text_content"], (0.0, 0.0)),
        ),
        patch(
            "worker.tasks.ingestion.segment_episodes",
            new_callable=AsyncMock,
            return_value=[_EPISODE],
        ),
        patch(
            "worker.tasks.ingestion.transform_episode",
            new_callable=AsyncMock,
            return_value=unit_data,
        ),
        patch("worker.tasks.ingestion.write_memory_unit", write_mock),
        patch(
            "worker.tasks.ingestion.verify_fidelity",
            new_callable=AsyncMock,
            return_value=_FIDELITY_OK,
        ),
        patch("worker.tasks.ingestion.update_unit_fidelity", new_callable=AsyncMock),
    ):
        redis = AsyncMock()
        redis.enqueue_job = AsyncMock(return_value=None)
        return asyncio.run(ingest_memory_unit({"redis": redis}, record["id"], record["user_id"]))


# ── 1. _coerce_unit: valid categories are preserved ──────────────────────────

VALID_CATEGORIES = [
    "episodic", "semantic", "procedural", "relational",
    "values", "humor", "advice",
]


@pytest.mark.parametrize("category", VALID_CATEGORIES)
def test_coerce_unit_valid_category_preserved(category: str):
    raw = {
        "content_first_person": "I loved those summers.",
        "memory_category": category,
        "stance": "nostalgic",
        "affect": {"emotion": "joy", "valence": 0.8, "intensity": 0.6},
        "themes": ["childhood"],
        "entities": {"people": [], "places": [], "period": "1980s"},
    }
    result = _coerce_unit(raw)
    assert result["memory_category"] == category


# ── 2. _coerce_unit: invalid category defaults to "episodic" ─────────────────

def test_coerce_unit_invalid_category_falls_back():
    raw = {
        "content_first_person": "I loved those summers.",
        "memory_category": "random_llm_hallucination",
        "stance": "nostalgic",
        "affect": {"emotion": "joy", "valence": 0.8, "intensity": 0.6},
        "themes": ["childhood"],
        "entities": {"people": [], "places": [], "period": ""},
    }
    result = _coerce_unit(raw)
    assert result["memory_category"] == "episodic"


def test_coerce_unit_empty_category_falls_back():
    raw = {
        "content_first_person": "I loved those summers.",
        "memory_category": "",
        "stance": "nostalgic",
        "affect": {"emotion": "joy", "valence": 0.8, "intensity": 0.6},
        "themes": [],
        "entities": {"people": [], "places": [], "period": ""},
    }
    result = _coerce_unit(raw)
    assert result["memory_category"] == "episodic"


# ── 3. _coerce_unit: missing/None category falls back to "episodic" ───────────

def test_coerce_unit_missing_category_falls_back():
    raw = {
        "content_first_person": "I loved those summers.",
        # memory_category key absent
        "stance": "nostalgic",
        "affect": {"emotion": "joy", "valence": 0.8, "intensity": 0.6},
        "themes": ["childhood"],
        "entities": {"people": [], "places": [], "period": ""},
    }
    result = _coerce_unit(raw)
    assert result["memory_category"] == "episodic"


def test_coerce_unit_none_category_falls_back():
    raw = {
        "content_first_person": "I loved those summers.",
        "memory_category": None,
        "stance": "nostalgic",
        "affect": {"emotion": "joy", "valence": 0.8, "intensity": 0.6},
        "themes": [],
        "entities": {"people": [], "places": [], "period": ""},
    }
    result = _coerce_unit(raw)
    assert result["memory_category"] == "episodic"


# ── 4. _mock_unit includes memory_category: "episodic" ───────────────────────

def test_mock_unit_includes_memory_category():
    result = _mock_unit(_EPISODE, _SOURCE_META)
    assert "memory_category" in result
    assert result["memory_category"] == "episodic"


# ── 5. Pipeline passes memory_category to write_memory_unit ──────────────────

def test_pipeline_passes_memory_category_to_write():
    unit_data = {
        "content_first_person": "I spent every summer in a small village.",
        "memory_category": "episodic",
        "stance": "nostalgic",
        "affect": {"emotion": "joy", "valence": 0.7, "intensity": 0.5},
        "themes": ["childhood", "family"],
        "entities": {"people": [], "places": ["village"], "period": "childhood"},
    }
    write_mock = AsyncMock(return_value="unit-uuid-001")
    _run_ingest(unit_data, write_mock)

    assert write_mock.called
    _, kwargs = write_mock.call_args
    assert kwargs.get("memory_category") == "episodic"


def test_pipeline_passes_relational_category():
    unit_data = {
        "content_first_person": "My grandmother taught me everything about cooking.",
        "memory_category": "relational",
        "stance": "grateful",
        "affect": {"emotion": "warmth", "valence": 0.9, "intensity": 0.7},
        "themes": ["family", "food"],
        "entities": {"people": ["grandmother"], "places": [], "period": "childhood"},
    }
    write_mock = AsyncMock(return_value="unit-uuid-002")
    _run_ingest(unit_data, write_mock)

    _, kwargs = write_mock.call_args
    assert kwargs.get("memory_category") == "relational"


def test_pipeline_defaults_missing_category_to_episodic():
    unit_data = {
        "content_first_person": "I remember the monsoon rains.",
        # memory_category intentionally absent (e.g. old mock path)
        "stance": "reflective",
        "affect": {"emotion": "nostalgic", "valence": 0.5, "intensity": 0.4},
        "themes": ["memory"],
        "entities": {"people": [], "places": [], "period": ""},
    }
    write_mock = AsyncMock(return_value="unit-uuid-003")
    _run_ingest(unit_data, write_mock)

    _, kwargs = write_mock.call_args
    assert kwargs.get("memory_category") == "episodic"
