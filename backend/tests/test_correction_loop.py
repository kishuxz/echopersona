"""Tests for step 5a: self-review correction loop (PERSONA_SPEC.md §7.1).

Coverage:
  - Flag routing for all four flag types (router layer)
  - wrong_fact creates a source_type="correction" memory_sources record
  - wrong_fact correction queues ingest_correction_unit (not ingest_memory_unit)
  - ingest_correction_unit sets supersedes + version=old+1 on produced units
  - get_memory_units_for_persona(exclude_superseded=True) hides superseded units
  - Unknown / missing target unit_id is rejected cleanly (router: 404)

All DB and LLM calls are mocked — no Supabase, no Redis, no real Groq.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.auth import get_current_user
from routers.review import router as review_router
from worker.tasks.ingestion import ingest_correction_unit


# ── Constants ─────────────────────────────────────────────────────────────────

_USER_ID = "user-1"
_PERSONA_ID = "persona-1"
_OLD_UNIT_ID = "unit-old-uuid"
_NEW_UNIT_ID = "unit-new-uuid"
_SRC_ID = "src-correction-uuid"

_PERSONA = {"id": _PERSONA_ID, "user_id": _USER_ID, "name": "Test"}

_OLD_UNIT = {
    "unit_id": _OLD_UNIT_ID,
    "persona_id": _PERSONA_ID,
    "version": 1,
    "supersedes": None,
    "source": {
        "source_question_id": "q_origins_01",
        "question_category": "origins",
        "question_text": "Where did you grow up?",
        "group_name": "",
        "modality": "text",
        "source_type": "answer",
    },
}

_CORRECTION_RECORD = {
    "id": _SRC_ID,
    "user_id": _USER_ID,
    "persona_id": _PERSONA_ID,
    "modality": "text",
    "question_category": "origins",
    "question_text": "Where did you grow up?",
    "source_question_id": "q_origins_01",
    "source_type": "correction",
    "media_ref": "",
    "captured_at": "",
    "file_id": "",
    "group_name": "",
    "text_content": "I grew up in Chennai, not Madurai.",
    "status": "pending",
}

_EPISODE = {"episode_text": "I grew up in Chennai, not Madurai."}
_UNIT_DATA = {
    "content_first_person": "I grew up in Chennai, not Madurai.",
    "stance": "corrective",
    "affect": {"emotion": "calm", "valence": 0.1, "intensity": 0.3},
    "themes": ["childhood", "origins"],
    "entities": {"people": [], "places": ["Chennai"], "period": "childhood"},
}
_FIDELITY_OK = {"flags": [], "fidelity_score": 1.0, "has_additions": False}


# ── Router test helpers ───────────────────────────────────────────────────────

def _make_client():
    """Build a TestClient for the review router with auth stubbed out."""
    app = FastAPI()
    app.include_router(review_router)
    app.dependency_overrides[get_current_user] = lambda: _USER_ID
    arq_mock = AsyncMock()
    arq_mock.enqueue_job = AsyncMock(return_value=MagicMock(job_id="job-xyz"))
    app.state.arq_pool = arq_mock
    return TestClient(app, raise_server_exceptions=True), arq_mock


def _mock_ctx() -> dict:
    redis = AsyncMock()
    redis.enqueue_job = AsyncMock(return_value=None)
    return {"redis": redis}


# ── Worker task helper ────────────────────────────────────────────────────────

def _run_ingest_correction(
    correction_record: dict,
    superseded_unit: dict | None,
    write_mock: AsyncMock,
) -> dict:
    """Run ingest_correction_unit with all I/O mocked; return its result dict."""
    with (
        patch(
            "worker.tasks.ingestion.get_source_record",
            new_callable=AsyncMock,
            return_value=correction_record,
        ),
        patch(
            "worker.tasks.ingestion.get_memory_unit",
            new_callable=AsyncMock,
            return_value=superseded_unit,
        ),
        patch("worker.tasks.ingestion.update_source_status", new_callable=AsyncMock),
        patch(
            "worker.tasks.ingestion.normalize_source",
            new_callable=AsyncMock,
            return_value=(correction_record["text_content"], (0.0, 0.0)),
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
        return asyncio.run(
            ingest_correction_unit(
                _mock_ctx(), _SRC_ID, _USER_ID, _OLD_UNIT_ID
            )
        )


# ── DB mock helper for retrieval tests ───────────────────────────────────────

def _make_retrieval_db(superseded_rows: list, unit_rows: list):
    """Build a mock DB for two-query get_memory_units_for_persona calls.

    First .execute() → superseded_rows (the 'which units are superseded' query)
    Second .execute() → unit_rows (the main units query, filtered)
    """
    results = [MagicMock(data=superseded_rows), MagicMock(data=unit_rows)]

    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.order.return_value = q
    q.not_.is_.return_value = q
    q.not_.in_.return_value = q
    q.execute.side_effect = results

    db = MagicMock()
    db.table.return_value = q
    return db, q


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Flag routing — all four types
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlagRouting:

    def test_good_flag_returns_none_action(self):
        client, _ = _make_client()
        with patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA):
            resp = client.post(
                f"/review/{_PERSONA_ID}/flag",
                json={"flag_type": "good"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"flag_type": "good", "action": "none"}

    def test_wrong_tone_flag_returns_logged(self):
        client, _ = _make_client()
        with patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA):
            resp = client.post(
                f"/review/{_PERSONA_ID}/flag",
                json={"flag_type": "wrong_tone", "unit_id": _OLD_UNIT_ID},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flag_type"] == "wrong_tone"
        assert data["action"] == "logged"

    def test_missing_flag_returns_logged(self):
        client, _ = _make_client()
        with patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA):
            resp = client.post(
                f"/review/{_PERSONA_ID}/flag",
                json={"flag_type": "missing", "question_category": "origins"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flag_type"] == "missing"
        assert data["action"] == "logged"

    def test_invalid_flag_type_is_rejected(self):
        client, _ = _make_client()
        with patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA):
            resp = client.post(
                f"/review/{_PERSONA_ID}/flag",
                json={"flag_type": "invented_type"},
            )
        assert resp.status_code == 400

    def test_unknown_persona_returns_404(self):
        client, _ = _make_client()
        with patch("routers.review.get_persona", new_callable=AsyncMock, return_value=None):
            resp = client.post(
                f"/review/{_PERSONA_ID}/flag",
                json={"flag_type": "good"},
            )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 2. wrong_fact router behaviour
# ═══════════════════════════════════════════════════════════════════════════════

class TestWrongFactRouter:

    def _post_wrong_fact(self, client, unit_id=_OLD_UNIT_ID, text="I grew up in Chennai."):
        return client.post(
            f"/review/{_PERSONA_ID}/flag",
            json={
                "flag_type": "wrong_fact",
                "unit_id": unit_id,
                "correction_text": text,
            },
        )

    def test_wrong_fact_creates_correction_source_record(self):
        client, _ = _make_client()
        with (
            patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA),
            patch("routers.review.get_memory_unit", new_callable=AsyncMock, return_value=_OLD_UNIT),
            patch(
                "routers.review.create_source_record",
                new_callable=AsyncMock,
                return_value=_SRC_ID,
            ) as mock_create,
        ):
            resp = self._post_wrong_fact(client)

        assert resp.status_code == 200
        # source_type must be "correction"
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["source_type"] == "correction"

    def test_wrong_fact_inherits_provenance_from_target_unit(self):
        client, _ = _make_client()
        with (
            patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA),
            patch("routers.review.get_memory_unit", new_callable=AsyncMock, return_value=_OLD_UNIT),
            patch(
                "routers.review.create_source_record",
                new_callable=AsyncMock,
                return_value=_SRC_ID,
            ) as mock_create,
        ):
            self._post_wrong_fact(client)

        kw = mock_create.call_args.kwargs
        assert kw["source_question_id"] == "q_origins_01"
        assert kw["question_category"] == "origins"
        assert kw["question_text"] == "Where did you grow up?"

    def test_wrong_fact_queues_ingest_correction_unit(self):
        client, arq_mock = _make_client()
        with (
            patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA),
            patch("routers.review.get_memory_unit", new_callable=AsyncMock, return_value=_OLD_UNIT),
            patch(
                "routers.review.create_source_record",
                new_callable=AsyncMock,
                return_value=_SRC_ID,
            ),
        ):
            resp = self._post_wrong_fact(client)

        assert resp.status_code == 200
        data = resp.json()
        assert data["flag_type"] == "wrong_fact"
        assert data["action"] == "correction_queued"
        assert data["supersedes_unit_id"] == _OLD_UNIT_ID
        # arq was called with the correction task name
        arq_mock.enqueue_job.assert_awaited_once()
        task_name = arq_mock.enqueue_job.call_args.args[0]
        assert task_name == "ingest_correction_unit"

    def test_wrong_fact_missing_unit_id_returns_400(self):
        client, _ = _make_client()
        with patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA):
            resp = client.post(
                f"/review/{_PERSONA_ID}/flag",
                json={"flag_type": "wrong_fact", "correction_text": "correction"},
            )
        assert resp.status_code == 400

    def test_wrong_fact_missing_correction_text_returns_400(self):
        client, _ = _make_client()
        with patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA):
            resp = client.post(
                f"/review/{_PERSONA_ID}/flag",
                json={"flag_type": "wrong_fact", "unit_id": _OLD_UNIT_ID},
            )
        assert resp.status_code == 400

    def test_wrong_fact_unknown_unit_id_returns_404(self):
        """A correction whose target unit_id does not exist must be rejected cleanly."""
        client, _ = _make_client()
        with (
            patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA),
            patch("routers.review.get_memory_unit", new_callable=AsyncMock, return_value=None),
        ):
            resp = self._post_wrong_fact(client, unit_id="nonexistent-unit-id")
        assert resp.status_code == 404

    def test_wrong_fact_cross_persona_unit_returns_404(self):
        """A unit belonging to a different persona must be rejected (no cross-persona leakage)."""
        other_persona_unit = {**_OLD_UNIT, "persona_id": "other-persona"}
        client, _ = _make_client()
        with (
            patch("routers.review.get_persona", new_callable=AsyncMock, return_value=_PERSONA),
            patch(
                "routers.review.get_memory_unit",
                new_callable=AsyncMock,
                return_value=other_persona_unit,
            ),
        ):
            resp = self._post_wrong_fact(client)
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ingest_correction_unit worker task
# ═══════════════════════════════════════════════════════════════════════════════

class TestIngestCorrectionUnit:

    def test_corrected_unit_sets_supersedes(self):
        write_mock = AsyncMock(return_value=_NEW_UNIT_ID)
        _run_ingest_correction(_CORRECTION_RECORD, _OLD_UNIT, write_mock)

        assert write_mock.call_args.kwargs["supersedes"] == _OLD_UNIT_ID

    def test_corrected_unit_version_is_old_plus_one(self):
        """version must be superseded.version + 1 (old=1 → new=2)."""
        write_mock = AsyncMock(return_value=_NEW_UNIT_ID)
        _run_ingest_correction(_CORRECTION_RECORD, _OLD_UNIT, write_mock)

        assert write_mock.call_args.kwargs["version"] == 2

    def test_version_increments_from_existing_version(self):
        """If the superseded unit is already v2, the correction must be v3."""
        v2_unit = {**_OLD_UNIT, "version": 2}
        write_mock = AsyncMock(return_value=_NEW_UNIT_ID)
        _run_ingest_correction(_CORRECTION_RECORD, v2_unit, write_mock)

        assert write_mock.call_args.kwargs["version"] == 3

    def test_source_type_correction_propagates_to_source_meta(self):
        write_mock = AsyncMock(return_value=_NEW_UNIT_ID)
        _run_ingest_correction(_CORRECTION_RECORD, _OLD_UNIT, write_mock)

        source_meta = write_mock.call_args.kwargs["source_meta"]
        assert source_meta["source_type"] == "correction"

    def test_correction_pipeline_returns_done(self):
        write_mock = AsyncMock(return_value=_NEW_UNIT_ID)
        result = _run_ingest_correction(_CORRECTION_RECORD, _OLD_UNIT, write_mock)

        assert result["status"] == "done"
        assert result["units_created"] == 1
        assert result["unit_ids"] == [_NEW_UNIT_ID]

    def test_unknown_superseded_unit_returns_error(self):
        """ingest_correction_unit must return an error dict (not raise) when the
        superseded unit does not exist in the DB."""
        write_mock = AsyncMock(return_value=_NEW_UNIT_ID)
        result = _run_ingest_correction(_CORRECTION_RECORD, None, write_mock)

        assert result["status"] == "error"
        assert result["reason"] == "superseded_unit_not_found"
        write_mock.assert_not_awaited()

    def test_missing_source_record_returns_error(self):
        with (
            patch(
                "worker.tasks.ingestion.get_source_record",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "worker.tasks.ingestion.get_memory_unit",
                new_callable=AsyncMock,
                return_value=_OLD_UNIT,
            ),
        ):
            result = asyncio.run(
                ingest_correction_unit(_mock_ctx(), "nonexistent", _USER_ID, _OLD_UNIT_ID)
            )

        assert result["status"] == "error"
        assert result["reason"] == "record_not_found"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Retrieval exclusion
# ═══════════════════════════════════════════════════════════════════════════════

class TestRetrievalExcludesSuperseded:

    def test_exclude_superseded_hides_old_unit(self):
        """get_memory_units_for_persona(exclude_superseded=True) must not return
        a unit whose unit_id is referenced by another unit's supersedes field."""
        from services.ingestion.source_store import get_memory_units_for_persona

        new_unit = {
            "unit_id": _NEW_UNIT_ID,
            "persona_id": _PERSONA_ID,
            "version": 2,
            "supersedes": _OLD_UNIT_ID,
            "content_first_person": "I grew up in Chennai.",
        }
        db, _ = _make_retrieval_db(
            superseded_rows=[{"supersedes": _OLD_UNIT_ID}],
            unit_rows=[new_unit],
        )
        with patch("services.ingestion.source_store.get_db", return_value=db):
            result = asyncio.run(
                get_memory_units_for_persona(_PERSONA_ID, exclude_superseded=True)
            )

        assert result == [new_unit]
        assert not any(u["unit_id"] == _OLD_UNIT_ID for u in result)

    def test_exclude_superseded_returns_new_unit(self):
        """The corrected (new) unit must appear in the retrieval result."""
        from services.ingestion.source_store import get_memory_units_for_persona

        new_unit = {
            "unit_id": _NEW_UNIT_ID,
            "persona_id": _PERSONA_ID,
            "version": 2,
            "supersedes": _OLD_UNIT_ID,
        }
        db, _ = _make_retrieval_db(
            superseded_rows=[{"supersedes": _OLD_UNIT_ID}],
            unit_rows=[new_unit],
        )
        with patch("services.ingestion.source_store.get_db", return_value=db):
            result = asyncio.run(
                get_memory_units_for_persona(_PERSONA_ID, exclude_superseded=True)
            )

        assert any(u["unit_id"] == _NEW_UNIT_ID for u in result)

    def test_no_superseded_units_returns_all(self):
        """When nothing is superseded the full list is returned unchanged."""
        from services.ingestion.source_store import get_memory_units_for_persona

        units = [
            {"unit_id": "unit-a", "persona_id": _PERSONA_ID, "version": 1},
            {"unit_id": "unit-b", "persona_id": _PERSONA_ID, "version": 1},
        ]
        db, _ = _make_retrieval_db(
            superseded_rows=[],  # nothing superseded
            unit_rows=units,
        )
        with patch("services.ingestion.source_store.get_db", return_value=db):
            result = asyncio.run(
                get_memory_units_for_persona(_PERSONA_ID, exclude_superseded=True)
            )

        assert result == units

    def test_exclude_superseded_false_skips_first_query(self):
        """When exclude_superseded=False the function must NOT issue the extra
        superseded-IDs query (one execute call, not two)."""
        from services.ingestion.source_store import get_memory_units_for_persona

        units = [{"unit_id": "unit-a", "persona_id": _PERSONA_ID, "version": 1}]
        db, q = _make_retrieval_db(superseded_rows=[], unit_rows=units)
        with patch("services.ingestion.source_store.get_db", return_value=db):
            asyncio.run(get_memory_units_for_persona(_PERSONA_ID, exclude_superseded=False))

        assert q.execute.call_count == 1
