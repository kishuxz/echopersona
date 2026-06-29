"""Tests for persona readiness gate: pipeline status updates and readiness endpoint.

Coverage:
  Pipeline (ingestion + enrichment):
  1. ingestion _run_pipeline sets readiness to 'processing' at start
  2. enrichment enrich_persona sets readiness to 'ready' on success
  3. ingestion _run_pipeline sets readiness to 'failed' on pipeline error
  4. enrichment enrich_persona sets readiness to 'failed' on enrichment error
  5. enrichment enrich_persona pops PERSONAS cache on success

  Endpoint (GET /persona/:id/readiness):
  6. Returns {ready: true, status: 'ready'} for a ready persona
  7. Returns {ready: false, status: 'processing'} for an in-progress persona
  8. Returns 401 without auth token
  9. Returns 404 for wrong owner (ownership enforcement)
  10. Returns 404 for nonexistent persona_id

All DB and LLM calls are mocked.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.persona import Persona
from routers.persona import router as persona_router
from worker.tasks.enrichment import enrich_persona

# ── helpers ───────────────────────────────────────────────────────────────────

_PERSONA_ID = "p-readiness-001"
_USER_ID = "u-readiness-001"

_UNITS = [{"content_first_person": "I grew up near the sea and loved sailing."}]


def _make_persona(readiness_status: str = "ready") -> Persona:
    return Persona(
        id=_PERSONA_ID,
        user_id=_USER_ID,
        name="Gran",
        stories=["I grew up near the sea."],
        personality_traits=["warm"],
        speaking_style="gentle",
        readiness_status=readiness_status,
    )


# ── 1. ingestion sets readiness to 'processing' at pipeline start ─────────────

def test_ingestion_sets_processing_on_start():
    from worker.tasks.ingestion import _run_pipeline

    record = {
        "id": "src-001",
        "persona_id": _PERSONA_ID,
        "modality": "text",
        "text_content": "I sailed the Atlantic at 22.",
        "file_id": "",
    }

    captured_calls: list[tuple[str, str]] = []

    async def mock_update_readiness(pid: str, status: str) -> None:
        captured_calls.append((pid, status))

    with (
        patch("worker.tasks.ingestion.update_source_status", new_callable=AsyncMock),
        patch("worker.tasks.ingestion.update_readiness_status", side_effect=mock_update_readiness),
        patch("worker.tasks.ingestion.normalize_source", new_callable=AsyncMock, return_value=("I sailed the Atlantic.", (0.0, 10.0))),
        patch("worker.tasks.ingestion.segment_episodes", new_callable=AsyncMock, return_value=[{"episode_text": "I sailed the Atlantic."}]),
        patch("worker.tasks.ingestion.transform_episode", new_callable=AsyncMock, return_value={
            "content_first_person": "I sailed the Atlantic at 22.",
            "stance": "reflective",
            "affect": {"emotion": "pride", "valence": 0.8, "intensity": 0.7},
            "themes": ["adventure"],
            "entities": {"people": [], "places": ["Atlantic"], "period": "age 22"},
            "memory_category": "episodic",
        }),
        patch("worker.tasks.ingestion.write_memory_unit", new_callable=AsyncMock, return_value="unit-001"),
        patch("worker.tasks.ingestion.verify_fidelity", new_callable=AsyncMock, return_value={
            "fidelity_score": 0.9,
            "flags": [],
            "has_additions": False,
        }),
        patch("worker.tasks.ingestion.update_unit_fidelity", new_callable=AsyncMock),
    ):
        ctx = {"redis": AsyncMock()}
        ctx["redis"].enqueue_job = AsyncMock()
        result = asyncio.run(_run_pipeline(ctx, record, _USER_ID))

    assert result["status"] == "done"
    # 'processing' must be the first readiness call
    assert captured_calls[0] == (_PERSONA_ID, "processing")


# ── 2. enrichment sets readiness to 'ready' on success ───────────────────────

def test_enrichment_sets_ready_on_success():
    entity_graph = [{"canonical": "Atlantic", "type": "place", "aliases": [], "description": ""}]
    exemplars = ["I sailed the Atlantic at 22."]
    voice_card = {"formality": "warm-casual", "catchphrases": [], "address_terms": [],
                  "humor_style": "", "sentence_rhythm": "", "emotional_tone": "",
                  "advice_style": "", "verbal_tics": []}

    captured_readiness: list[tuple[str, str]] = []

    async def mock_update_readiness(pid: str, status: str) -> None:
        captured_readiness.append((pid, status))

    _blank_identity = {"values": [], "worldview": "", "role_identity": "", "emotional_wiring": "", "communication_style": "", "life_philosophy": ""}

    with (
        patch("worker.tasks.enrichment.get_memory_units_for_persona", new_callable=AsyncMock, return_value=_UNITS),
        patch("worker.tasks.enrichment.build_entity_graph", new_callable=AsyncMock, return_value=entity_graph),
        patch("worker.tasks.enrichment.update_entity_graph", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.extract_style_exemplars", new_callable=AsyncMock, return_value=(exemplars, voice_card)),
        patch("worker.tasks.enrichment.update_style_exemplars", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.update_voice_card", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.extract_identity_card", new_callable=AsyncMock, return_value=_blank_identity),
        patch("worker.tasks.enrichment.update_identity_card", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.update_readiness_status", side_effect=mock_update_readiness),
        patch("worker.tasks.enrichment.RAG_INDICES", {}),
        patch("worker.tasks.enrichment.PERSONAS", {}),
    ):
        result = asyncio.run(enrich_persona({}, _PERSONA_ID))

    assert result["status"] == "done"
    assert captured_readiness == [(_PERSONA_ID, "ready")]


# ── 3. ingestion sets readiness to 'failed' on pipeline error ─────────────────

def test_ingestion_sets_failed_on_error():
    record = {
        "id": "src-002",
        "persona_id": _PERSONA_ID,
        "modality": "text",
        "text_content": "Some text.",
        "file_id": "",
    }

    captured_readiness: list[tuple[str, str]] = []

    async def mock_update_readiness(pid: str, status: str) -> None:
        captured_readiness.append((pid, status))

    with (
        patch("worker.tasks.ingestion.update_source_status", new_callable=AsyncMock),
        patch("worker.tasks.ingestion.update_readiness_status", side_effect=mock_update_readiness),
        patch("worker.tasks.ingestion.normalize_source", new_callable=AsyncMock, side_effect=RuntimeError("Groq timeout")),
    ):
        ctx = {"redis": AsyncMock()}
        result = asyncio.run(_run_pipeline_from_ingestion(ctx, record, _USER_ID))

    assert result["status"] == "error"
    statuses = [s for _, s in captured_readiness]
    assert "processing" in statuses
    assert "failed" in statuses
    assert statuses.index("processing") < statuses.index("failed")


def _run_pipeline_from_ingestion(ctx, record, user_id):
    from worker.tasks.ingestion import _run_pipeline
    return _run_pipeline(ctx, record, user_id)


# ── 4. enrichment sets readiness to 'failed' on enrichment error ──────────────

def test_enrichment_sets_failed_on_error():
    captured_readiness: list[tuple[str, str]] = []

    async def mock_update_readiness(pid: str, status: str) -> None:
        captured_readiness.append((pid, status))

    with (
        patch("worker.tasks.enrichment.get_memory_units_for_persona", new_callable=AsyncMock, return_value=_UNITS),
        patch("worker.tasks.enrichment.build_entity_graph", new_callable=AsyncMock, side_effect=RuntimeError("LLM error")),
        patch("worker.tasks.enrichment.update_readiness_status", side_effect=mock_update_readiness),
        patch("worker.tasks.enrichment.RAG_INDICES", {}),
        patch("worker.tasks.enrichment.PERSONAS", {}),
    ):
        result = asyncio.run(enrich_persona({}, _PERSONA_ID))

    assert result["status"] == "error"
    assert captured_readiness == [(_PERSONA_ID, "failed")]


# ── 5. enrichment pops PERSONAS cache on success ──────────────────────────────

def test_enrichment_pops_personas_cache():
    entity_graph = []
    exemplars = ["A phrase."]
    voice_card = {"formality": "warm-casual", "catchphrases": [], "address_terms": [],
                  "humor_style": "", "sentence_rhythm": "", "emotional_tone": "",
                  "advice_style": "", "verbal_tics": []}
    personas_cache = {_PERSONA_ID: _make_persona()}

    _blank_identity = {"values": [], "worldview": "", "role_identity": "", "emotional_wiring": "", "communication_style": "", "life_philosophy": ""}

    with (
        patch("worker.tasks.enrichment.get_memory_units_for_persona", new_callable=AsyncMock, return_value=_UNITS),
        patch("worker.tasks.enrichment.build_entity_graph", new_callable=AsyncMock, return_value=entity_graph),
        patch("worker.tasks.enrichment.update_entity_graph", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.extract_style_exemplars", new_callable=AsyncMock, return_value=(exemplars, voice_card)),
        patch("worker.tasks.enrichment.update_style_exemplars", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.update_voice_card", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.extract_identity_card", new_callable=AsyncMock, return_value=_blank_identity),
        patch("worker.tasks.enrichment.update_identity_card", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.update_readiness_status", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.RAG_INDICES", {_PERSONA_ID: object()}),
        patch("worker.tasks.enrichment.PERSONAS", personas_cache),
    ):
        asyncio.run(enrich_persona({}, _PERSONA_ID))

    assert _PERSONA_ID not in personas_cache


# ── Endpoint tests (GET /persona/:id/readiness) ───────────────────────────────

from middleware.auth import get_current_user


def _make_test_client(user_id: str | None = _USER_ID) -> TestClient:
    app = FastAPI()
    app.include_router(persona_router)
    if user_id is not None:
        app.dependency_overrides[get_current_user] = lambda: user_id
    return TestClient(app, raise_server_exceptions=False)


def _patch_sources(done: int = 1, total: int = 1):
    rows = [{"status": "done"}] * done + [{"status": "processing"}] * (total - done)
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = rows
    return patch("routers.persona.get_db", return_value=mock_db)


# ── 6. Ready persona returns {ready: true, status: 'ready'} ──────────────────

def test_readiness_endpoint_returns_ready():
    persona = _make_persona(readiness_status="ready")
    client = _make_test_client()

    with (
        patch("routers.persona.persona_store") as mock_store,
        _patch_sources(done=2, total=2),
    ):
        mock_store.get_persona = AsyncMock(return_value=persona)
        res = client.get(f"/persona/{_PERSONA_ID}/readiness")

    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is True
    assert body["status"] == "ready"
    assert body["sources_done"] == 2
    assert body["sources_total"] == 2


# ── 7. Processing persona returns {ready: false, status: 'processing'} ────────

def test_readiness_endpoint_returns_processing():
    persona = _make_persona(readiness_status="processing")
    client = _make_test_client()

    with (
        patch("routers.persona.persona_store") as mock_store,
        _patch_sources(done=1, total=3),
    ):
        mock_store.get_persona = AsyncMock(return_value=persona)
        res = client.get(f"/persona/{_PERSONA_ID}/readiness")

    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is False
    assert body["status"] == "processing"
    assert body["sources_done"] == 1
    assert body["sources_total"] == 3


# ── 8. No auth override (unauthenticated) → 401 or 422 ───────────────────────

def test_readiness_endpoint_requires_auth():
    client = _make_test_client(user_id=None)
    res = client.get(f"/persona/{_PERSONA_ID}/readiness")
    assert res.status_code in (401, 422)


# ── 9. Wrong owner → 404 (ownership enforcement) ─────────────────────────────

def test_readiness_endpoint_enforces_ownership():
    client = _make_test_client(user_id="attacker-uid")

    with patch("routers.persona.persona_store") as mock_store:
        mock_store.get_persona = AsyncMock(return_value=None)
        res = client.get(f"/persona/{_PERSONA_ID}/readiness")

    assert res.status_code == 404


# ── 10. Nonexistent persona_id → 404 ─────────────────────────────────────────

def test_readiness_endpoint_not_found():
    client = _make_test_client()

    with patch("routers.persona.persona_store") as mock_store:
        mock_store.get_persona = AsyncMock(return_value=None)
        res = client.get("/persona/does-not-exist/readiness")

    assert res.status_code == 404
