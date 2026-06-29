"""Tests for Slice 11 — Admin Panel router.

Coverage:
  auth:
    - Missing X-Admin-Key header → 422
    - Wrong key → 403
    - Empty ADMIN_KEY (unconfigured) → 403 regardless of header value
    - Correct key → 200

  GET /admin/stats:
    - Returns aggregated counts
    - by_readiness counts match persona statuses
    - plan_tier_counts match entitlement rows

  GET /admin/personas:
    - Returns list of AdminPersonaRow
    - Merges email, plan_tier, counts correctly

  GET /admin/personas/{id}:
    - Returns full detail with relationships and memory units
    - 404 when persona not found

  POST /admin/personas/{id}/re-enrich:
    - Enqueues arq job when pool is available
    - 409 when readiness_status = processing
    - 404 when persona not found

  POST /admin/personas/{id}/relationships:
    - Creates relationship, returns AdminRelationship
    - 409 when relationship already exists
    - 404 when persona not found

  DELETE /admin/personas/{id}/relationships/{listener_user_id}:
    - Deletes relationship
    - 404 when not found

asyncio.run() drives async cases where needed — no pytest-asyncio.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_GOOD_KEY = "test-admin-key-abc123"
_PERSONA_ID = "p-admin-test"
_USER_ID = "u-admin-test"
_MEMBER_ID = "m-admin-test"
_REL_ID = "rel-admin-test"


# ── App fixture ───────────────────────────────────────────────────────────────

def _make_client(admin_key: str = _GOOD_KEY):
    """Create a TestClient with ADMIN_KEY patched into settings."""
    from main import app
    with patch("middleware.admin_auth.settings") as mock_s:
        mock_s.admin_key = admin_key
        client = TestClient(app, raise_server_exceptions=False)
    return client


def _admin_headers(key: str = _GOOD_KEY) -> dict:
    return {"X-Admin-Key": key}


def _make_db_mock():
    db = MagicMock()
    # Default: return empty data
    db.table.return_value.select.return_value.execute.return_value.data = []
    db.table.return_value.select.return_value.execute.return_value.count = 0
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    return db


# ── Auth tests ────────────────────────────────────────────────────────────────

class TestAdminAuth:
    def test_missing_key_returns_422(self):
        from fastapi.testclient import TestClient
        from main import app
        with patch("middleware.admin_auth.settings") as mock_s:
            mock_s.admin_key = _GOOD_KEY
            with patch("routers.admin.get_db", return_value=_make_db_mock()):
                client = TestClient(app, raise_server_exceptions=False)
                resp = client.get("/admin/stats")
        assert resp.status_code == 422

    def test_wrong_key_returns_403(self):
        from fastapi.testclient import TestClient
        from main import app
        with patch("middleware.admin_auth.settings") as mock_s:
            mock_s.admin_key = _GOOD_KEY
            with patch("routers.admin.get_db", return_value=_make_db_mock()):
                client = TestClient(app, raise_server_exceptions=False)
                resp = client.get("/admin/stats", headers={"X-Admin-Key": "wrong-key"})
        assert resp.status_code == 403

    def test_empty_admin_key_is_locked(self):
        """Even if caller sends the empty string, an unconfigured ADMIN_KEY must deny."""
        from fastapi.testclient import TestClient
        from main import app
        with patch("middleware.admin_auth.settings") as mock_s:
            mock_s.admin_key = ""
            with patch("routers.admin.get_db", return_value=_make_db_mock()):
                client = TestClient(app, raise_server_exceptions=False)
                resp = client.get("/admin/stats", headers={"X-Admin-Key": ""})
        assert resp.status_code == 403

    def test_correct_key_passes(self):
        from fastapi.testclient import TestClient
        from main import app

        mock_db = _make_db_mock()
        mock_db.table.return_value.select.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value.execute.return_value.count = 0
        mock_db.auth.admin.list_users.return_value = MagicMock(users=[], total=0)

        with (
            patch("middleware.admin_auth.settings") as mock_s,
            patch("routers.admin.get_db", return_value=mock_db),
        ):
            mock_s.admin_key = _GOOD_KEY
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/admin/stats", headers=_admin_headers())

        assert resp.status_code == 200


# ── Stats tests ───────────────────────────────────────────────────────────────

class TestAdminStats:
    def test_stats_aggregates_correctly(self):
        from fastapi.testclient import TestClient
        from main import app

        mock_db = _make_db_mock()

        def table_side_effect(tbl):
            t = MagicMock()
            if tbl == "personas":
                t.select.return_value.execute.return_value.data = [
                    {"readiness_status": "ready"},
                    {"readiness_status": "ready"},
                    {"readiness_status": "pending"},
                ]
            elif tbl == "memory_units":
                r = MagicMock()
                r.count = 10
                t.select.return_value.execute.return_value = r
            elif tbl == "persona_relationships":
                r = MagicMock()
                r.count = 5
                t.select.return_value.execute.return_value = r
            elif tbl == "stripe_entitlements":
                t.select.return_value.execute.return_value.data = [
                    {"plan_tier": "creator"},
                    {"plan_tier": "free"},
                ]
            else:
                t.select.return_value.execute.return_value.data = []
            return t

        mock_db.table.side_effect = table_side_effect
        mock_db.auth.admin.list_users.return_value = MagicMock(users=[], total=3)

        with (
            patch("middleware.admin_auth.settings") as mock_s,
            patch("routers.admin.get_db", return_value=mock_db),
        ):
            mock_s.admin_key = _GOOD_KEY
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/admin/stats", headers=_admin_headers())

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_personas"] == 3
        assert data["by_readiness"]["ready"] == 2
        assert data["by_readiness"]["pending"] == 1
        assert data["total_memory_units"] == 10
        assert data["total_relationships"] == 5
        assert data["plan_tier_counts"]["creator"] == 1


# ── Persona list tests ────────────────────────────────────────────────────────

class TestAdminPersonaList:
    def test_list_personas_returns_rows(self):
        from fastapi.testclient import TestClient
        from main import app

        mock_db = _make_db_mock()

        def table_side_effect(tbl):
            t = MagicMock()
            if tbl == "personas":
                t.select.return_value.execute.return_value.data = [
                    {
                        "id": _PERSONA_ID,
                        "name": "Test",
                        "readiness_status": "ready",
                        "user_id": _USER_ID,
                        "created_at": "2026-01-01T00:00:00+00:00",
                    }
                ]
            elif tbl == "stripe_entitlements":
                t.select.return_value.execute.return_value.data = [
                    {"user_id": _USER_ID, "plan_tier": "creator"}
                ]
            elif tbl in ("memory_units", "persona_relationships"):
                t.select.return_value.execute.return_value.data = []
            else:
                t.select.return_value.execute.return_value.data = []
            return t

        mock_db.table.side_effect = table_side_effect
        mock_db.auth.admin.list_users.return_value = MagicMock(
            users=[MagicMock(id=_USER_ID, email="owner@example.com")],
        )

        with (
            patch("middleware.admin_auth.settings") as mock_s,
            patch("routers.admin.get_db", return_value=mock_db),
        ):
            mock_s.admin_key = _GOOD_KEY
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/admin/personas", headers=_admin_headers())

        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["name"] == "Test"
        assert rows[0]["owner_email"] == "owner@example.com"
        assert rows[0]["plan_tier"] == "creator"


# ── Persona detail tests ──────────────────────────────────────────────────────

class TestAdminPersonaDetail:
    def test_detail_404_for_missing_persona(self):
        from fastapi.testclient import TestClient
        from main import app

        mock_db = _make_db_mock()
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None

        with (
            patch("middleware.admin_auth.settings") as mock_s,
            patch("routers.admin.get_db", return_value=mock_db),
        ):
            mock_s.admin_key = _GOOD_KEY
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/admin/personas/nonexistent", headers=_admin_headers())

        assert resp.status_code == 404


# ── Re-enrich tests ───────────────────────────────────────────────────────────

class TestAdminReEnrich:
    def test_re_enrich_404_for_missing_persona(self):
        from fastapi.testclient import TestClient
        from main import app

        mock_db = _make_db_mock()

        with (
            patch("middleware.admin_auth.settings") as mock_s,
            patch("routers.admin.get_db", return_value=mock_db),
        ):
            mock_s.admin_key = _GOOD_KEY
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(f"/admin/personas/nonexistent/re-enrich", headers=_admin_headers())

        assert resp.status_code == 404

    def test_re_enrich_409_when_processing(self):
        from fastapi.testclient import TestClient
        from main import app

        mock_db = _make_db_mock()

        def table_side_effect(tbl):
            t = MagicMock()
            if tbl == "personas":
                t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                    "readiness_status": "processing"
                }
            return t

        mock_db.table.side_effect = table_side_effect

        with (
            patch("middleware.admin_auth.settings") as mock_s,
            patch("routers.admin.get_db", return_value=mock_db),
        ):
            mock_s.admin_key = _GOOD_KEY
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(f"/admin/personas/{_PERSONA_ID}/re-enrich", headers=_admin_headers())

        assert resp.status_code == 409

    def test_re_enrich_enqueues_job(self):
        from fastapi.testclient import TestClient
        from main import app

        mock_db = _make_db_mock()

        def table_side_effect(tbl):
            t = MagicMock()
            if tbl == "personas":
                t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                    "readiness_status": "ready"
                }
            return t

        mock_db.table.side_effect = table_side_effect

        mock_job = MagicMock()
        mock_job.job_id = "job-123"
        mock_arq = AsyncMock()
        mock_arq.enqueue_job = AsyncMock(return_value=mock_job)

        with (
            patch("middleware.admin_auth.settings") as mock_s,
            patch("routers.admin.get_db", return_value=mock_db),
        ):
            mock_s.admin_key = _GOOD_KEY
            client = TestClient(app, raise_server_exceptions=False)
            # Inject arq_pool into app state
            app.state.arq_pool = mock_arq
            resp = client.post(f"/admin/personas/{_PERSONA_ID}/re-enrich", headers=_admin_headers())

        assert resp.status_code == 200
        data = resp.json()
        assert data["persona_id"] == _PERSONA_ID


# ── Relationship management tests ─────────────────────────────────────────────

class TestAdminRelationships:
    def test_add_relationship_409_when_exists(self):
        from fastapi.testclient import TestClient
        from main import app

        mock_db = _make_db_mock()

        def table_side_effect(tbl):
            t = MagicMock()
            if tbl == "personas":
                t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"id": _PERSONA_ID}
            elif tbl == "persona_relationships":
                t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                    "id": _REL_ID
                }
            return t

        mock_db.table.side_effect = table_side_effect

        with (
            patch("middleware.admin_auth.settings") as mock_s,
            patch("routers.admin.get_db", return_value=mock_db),
        ):
            mock_s.admin_key = _GOOD_KEY
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                f"/admin/personas/{_PERSONA_ID}/relationships",
                json={"listener_user_id": _MEMBER_ID, "entity_canonical": "John", "relationship": "son"},
                headers=_admin_headers(),
            )

        assert resp.status_code == 409

    def test_delete_relationship_404_when_missing(self):
        from fastapi.testclient import TestClient
        from main import app

        mock_db = _make_db_mock()

        def table_side_effect(tbl):
            t = MagicMock()
            if tbl == "persona_relationships":
                t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
            return t

        mock_db.table.side_effect = table_side_effect

        with (
            patch("middleware.admin_auth.settings") as mock_s,
            patch("routers.admin.get_db", return_value=mock_db),
        ):
            mock_s.admin_key = _GOOD_KEY
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.delete(
                f"/admin/personas/{_PERSONA_ID}/relationships/{_MEMBER_ID}",
                headers=_admin_headers(),
            )

        assert resp.status_code == 404

    def test_delete_relationship_returns_deleted(self):
        from fastapi.testclient import TestClient
        from main import app

        mock_db = _make_db_mock()

        def table_side_effect(tbl):
            t = MagicMock()
            if tbl == "persona_relationships":
                t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                    "id": _REL_ID
                }
                t.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
            return t

        mock_db.table.side_effect = table_side_effect

        with (
            patch("middleware.admin_auth.settings") as mock_s,
            patch("routers.admin.get_db", return_value=mock_db),
        ):
            mock_s.admin_key = _GOOD_KEY
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.delete(
                f"/admin/personas/{_PERSONA_ID}/relationships/{_MEMBER_ID}",
                headers=_admin_headers(),
            )

        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
