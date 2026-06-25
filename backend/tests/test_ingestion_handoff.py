"""Tests for the creation → ingestion handoff (build step 4, PERSONA_SPEC.md §6).

Verifies that §2.3 [add-004] provenance fields (source_question_id, source_type,
media_ref, captured_at, persona_id, version, supersedes) propagate intact from the
memory_sources record through ingest_memory_unit into the write_memory_unit call.

All DB and LLM calls are mocked — no Redis, no Supabase, no real Groq.

NOTE: migration 004 (backend/migrations/004_creation_fields.sql) must be applied
in the Supabase SQL editor before these paths are exercised against a live DB.
Unit tests here do NOT require it.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

from worker.tasks.ingestion import _source_meta, ingest_memory_unit


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _source_record(
    source_question_id: str = "q_origins_01",
    source_type: str = "answer",
    media_ref: str = "",
    captured_at: str = "2026-06-16T12:00:00+00:00",
    persona_id: str = "p1",
    modality: str = "text",
    text_content: str = "I grew up in Madurai, near the big temple.",
) -> dict:
    return {
        "id": "src-uuid-001",
        "user_id": "u1",
        "persona_id": persona_id,
        "modality": modality,
        "question_category": "origins",
        "question_text": "Where did you grow up?",
        "source_question_id": source_question_id,
        "source_type": source_type,
        "media_ref": media_ref,
        "captured_at": captured_at,
        "file_id": "",
        "group_name": "",
        "text_content": text_content,
        "status": "pending",
    }


def _mock_ctx() -> dict:
    redis = AsyncMock()
    redis.enqueue_job = AsyncMock(return_value=None)
    return {"redis": redis}


_EPISODE = {"episode_text": "I grew up near a temple in Madurai."}
_UNIT_DATA = {
    "content_first_person": "I grew up near a temple in Madurai.",
    "stance": "nostalgic",
    "affect": {"emotion": "nostalgic", "valence": 0.5, "intensity": 0.4},
    "themes": ["childhood"],
    "entities": {"people": [], "places": ["Madurai"], "period": "childhood"},
}
_FIDELITY_OK = {"flags": [], "fidelity_score": 1.0, "has_additions": False}


def _run_ingest(record: dict, write_mock: AsyncMock) -> dict:
    """Run the full ingest pipeline with all I/O mocked; return its result dict."""
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
            return_value=_UNIT_DATA,
        ),
        patch("worker.tasks.ingestion.write_memory_unit", write_mock),
        patch(
            "worker.tasks.ingestion.verify_fidelity",
            new_callable=AsyncMock,
            return_value=_FIDELITY_OK,
        ),
        patch("worker.tasks.ingestion.update_unit_fidelity", new_callable=AsyncMock),
    ):
        return asyncio.run(ingest_memory_unit(_mock_ctx(), record["id"], record["user_id"]))


# ── _source_meta unit tests (pure, synchronous) ───────────────────────────────


def test_source_meta_propagates_source_question_id():
    record = _source_record()
    meta = _source_meta(record, (0.0, 0.0))
    assert meta["source_question_id"] == "q_origins_01"


def test_source_meta_propagates_source_type():
    record = _source_record(source_type="answer")
    meta = _source_meta(record, (0.0, 0.0))
    assert meta["source_type"] == "answer"


def test_source_meta_defaults_source_type_when_missing():
    record = _source_record()
    record.pop("source_type")
    meta = _source_meta(record, (0.0, 0.0))
    assert meta["source_type"] == "answer"


def test_source_meta_propagates_media_ref():
    ref = "storage://ingestion-sources/u1/abc.mp4"
    meta = _source_meta(_source_record(media_ref=ref), (0.0, 3.5))
    assert meta["media_ref"] == ref


def test_source_meta_propagates_captured_at():
    ts = "2026-06-16T12:00:00+00:00"
    meta = _source_meta(_source_record(captured_at=ts), (0.0, 0.0))
    assert meta["captured_at"] == ts


def test_source_meta_propagates_timestamp_range():
    meta = _source_meta(_source_record(), (1.5, 8.2))
    assert meta["timestamp_range"] == [1.5, 8.2]


def test_source_meta_propagates_question_category_and_modality():
    meta = _source_meta(_source_record(), (0.0, 0.0))
    assert meta["question_category"] == "origins"
    assert meta["modality"] == "text"


# ── ingest_memory_unit provenance tests (async via asyncio.run) ───────────────


def test_ingest_propagates_source_question_id():
    write_mock = AsyncMock(return_value="unit-uuid-001")
    _run_ingest(_source_record(source_question_id="q_origins_01"), write_mock)

    source_meta = write_mock.call_args.kwargs["source_meta"]
    assert source_meta["source_question_id"] == "q_origins_01"


def test_ingest_source_question_id_traces_to_question_bank():
    """source_question_id written at Stage 0 must be a real question bank ID."""
    from services.question_bank import get_question
    write_mock = AsyncMock(return_value="unit-uuid-001")
    _run_ingest(_source_record(source_question_id="q_origins_01"), write_mock)

    qid = write_mock.call_args.kwargs["source_meta"]["source_question_id"]
    assert get_question(qid) is not None, f"{qid!r} not found in question bank"


def test_ingest_source_type_defaults_to_answer():
    write_mock = AsyncMock(return_value="unit-uuid-001")
    _run_ingest(_source_record(source_type="answer"), write_mock)

    assert write_mock.call_args.kwargs["source_meta"]["source_type"] == "answer"


def test_ingest_propagates_media_ref():
    ref = "storage://ingestion-sources/u1/abc.mp4"
    write_mock = AsyncMock(return_value="unit-uuid-001")
    _run_ingest(_source_record(media_ref=ref), write_mock)

    assert write_mock.call_args.kwargs["source_meta"]["media_ref"] == ref


def test_ingest_propagates_captured_at():
    ts = "2026-06-16T12:00:00+00:00"
    write_mock = AsyncMock(return_value="unit-uuid-001")
    _run_ingest(_source_record(captured_at=ts), write_mock)

    assert write_mock.call_args.kwargs["source_meta"]["captured_at"] == ts


def test_ingest_propagates_persona_id():
    write_mock = AsyncMock(return_value="unit-uuid-001")
    _run_ingest(_source_record(persona_id="p-specific"), write_mock)

    assert write_mock.call_args.kwargs["persona_id"] == "p-specific"


def test_ingest_version_is_1():
    write_mock = AsyncMock(return_value="unit-uuid-001")
    _run_ingest(_source_record(), write_mock)

    assert write_mock.call_args.kwargs["version"] == 1


def test_ingest_supersedes_is_none():
    write_mock = AsyncMock(return_value="unit-uuid-001")
    _run_ingest(_source_record(), write_mock)

    assert write_mock.call_args.kwargs["supersedes"] is None


def test_ingest_returns_done_with_correct_unit_ids():
    write_mock = AsyncMock(return_value="unit-uuid-001")
    result = _run_ingest(_source_record(), write_mock)

    assert result["status"] == "done"
    assert result["units_created"] == 1
    assert result["unit_ids"] == ["unit-uuid-001"]


def test_ingest_empty_text_returns_zero_units():
    record = _source_record(text_content="")
    with (
        patch("worker.tasks.ingestion.get_source_record", new_callable=AsyncMock, return_value=record),
        patch("worker.tasks.ingestion.update_source_status", new_callable=AsyncMock),
        patch(
            "worker.tasks.ingestion.normalize_source",
            new_callable=AsyncMock,
            return_value=("", (0.0, 0.0)),
        ),
    ):
        result = asyncio.run(ingest_memory_unit(_mock_ctx(), record["id"], record["user_id"]))

    assert result["status"] == "done"
    assert result["units_created"] == 0


def test_ingest_missing_source_record_returns_error():
    with patch("worker.tasks.ingestion.get_source_record", new_callable=AsyncMock, return_value=None):
        result = asyncio.run(ingest_memory_unit(_mock_ctx(), "nonexistent", "u1"))

    assert result["status"] == "error"
    assert result["reason"] == "record_not_found"


def test_ingest_video_audio_with_text_content_completes():
    """video_audio source with typed text_content ingests successfully (APJ failure path)."""
    record = _source_record(
        modality="video_audio",
        text_content="I grew up in Chennai, near the Marina beach.",
    )
    write_mock = AsyncMock(return_value="unit-uuid-va-001")
    result = _run_ingest(record, write_mock)

    assert result["status"] == "done"
    assert result["units_created"] == 1
    assert result["unit_ids"] == ["unit-uuid-va-001"]


def test_ingest_video_audio_empty_text_no_file_returns_zero_units():
    """video_audio source with empty text and no file completes cleanly with 0 units (no crash)."""
    record = _source_record(modality="video_audio", text_content="")
    with (
        patch("worker.tasks.ingestion.get_source_record", new_callable=AsyncMock, return_value=record),
        patch("worker.tasks.ingestion.update_source_status", new_callable=AsyncMock),
        patch(
            "worker.tasks.ingestion.normalize_source",
            new_callable=AsyncMock,
            return_value=("", (0.0, 0.0)),
        ),
    ):
        result = asyncio.run(ingest_memory_unit(_mock_ctx(), record["id"], record["user_id"]))

    assert result["status"] == "done"
    assert result["units_created"] == 0


def test_ingest_episode_failure_skips_episode_but_continues():
    """A per-episode transform error should not abort the whole pipeline."""
    record = _source_record()
    two_episodes = [
        {"episode_text": "Episode one."},
        {"episode_text": "Episode two."},
    ]
    unit_data_good = dict(_UNIT_DATA)

    write_mock = AsyncMock(return_value="unit-uuid-002")

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
            return_value=two_episodes,
        ),
        patch(
            "worker.tasks.ingestion.transform_episode",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("Stage 2 failed"), unit_data_good],
        ),
        patch("worker.tasks.ingestion.write_memory_unit", write_mock),
        patch(
            "worker.tasks.ingestion.verify_fidelity",
            new_callable=AsyncMock,
            return_value=_FIDELITY_OK,
        ),
        patch("worker.tasks.ingestion.update_unit_fidelity", new_callable=AsyncMock),
    ):
        result = asyncio.run(ingest_memory_unit(_mock_ctx(), record["id"], record["user_id"]))

    # First episode fails, second succeeds → 1 unit created
    assert result["status"] == "done"
    assert result["units_created"] == 1
