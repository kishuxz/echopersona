"""Tests for Slice 4: Listener Profiles.

Covers:
  - resolve_unit_entity_ids (Stage 3 back-link builder)
  - PersonaRAG.retrieve score threshold (§9.7)
  - PersonaRAG.retrieve listener_entity boost (§9.3)
  - resolved_entity_ids stored in RAG index units
  - ListenerContext.entity_canonical field
"""
import pytest
from services.ingestion.stage3 import resolve_unit_entity_ids
from services.rag import PersonaRAG, _SCORE_THRESHOLD, _ENTITY_BOOST
from models.consent import ListenerContext, ModalityConsent


# ── resolve_unit_entity_ids ────────────────────────────────────────────────

ENTITY_GRAPH = [
    {
        "canonical": "Grandma Rose",
        "type": "person",
        "aliases": ["Grandma", "Rose", "Grandma Rose"],
        "description": "maternal grandmother",
    },
    {
        "canonical": "Brooklyn",
        "type": "place",
        "aliases": ["Brooklyn", "the old neighbourhood"],
        "description": "childhood neighbourhood",
    },
    {
        "canonical": "Father",
        "type": "person",
        "aliases": ["Dad", "my father", "Father"],
        "description": "persona's father",
    },
]


def _make_unit(uid: str, people: list[str] = (), places: list[str] = ()) -> dict:
    return {
        "unit_id": uid,
        "entities": {"people": list(people), "places": list(places)},
    }


def test_resolve_known_alias():
    units = [_make_unit("u1", people=["Grandma", "Dad"])]
    result = resolve_unit_entity_ids(units, ENTITY_GRAPH)
    assert set(result["u1"]) == {"Grandma Rose", "Father"}


def test_resolve_canonical_name_itself():
    units = [_make_unit("u2", people=["Grandma Rose"])]
    result = resolve_unit_entity_ids(units, ENTITY_GRAPH)
    assert result["u2"] == ["Grandma Rose"]


def test_resolve_place_entity():
    units = [_make_unit("u3", places=["Brooklyn"])]
    result = resolve_unit_entity_ids(units, ENTITY_GRAPH)
    assert result["u3"] == ["Brooklyn"]


def test_resolve_unknown_mention_excluded():
    units = [_make_unit("u4", people=["Aunt Mary"])]
    result = resolve_unit_entity_ids(units, ENTITY_GRAPH)
    assert result["u4"] == []


def test_resolve_empty_entities():
    units = [_make_unit("u5")]
    result = resolve_unit_entity_ids(units, ENTITY_GRAPH)
    assert result["u5"] == []


def test_resolve_case_insensitive():
    units = [_make_unit("u6", people=["grandma"])]
    result = resolve_unit_entity_ids(units, ENTITY_GRAPH)
    assert result["u6"] == ["Grandma Rose"]


def test_resolve_multiple_units():
    units = [
        _make_unit("u7", people=["my father"]),
        _make_unit("u8", places=["the old neighbourhood"]),
        _make_unit("u9", people=["Unknown Person"]),
    ]
    result = resolve_unit_entity_ids(units, ENTITY_GRAPH)
    assert result["u7"] == ["Father"]
    assert result["u8"] == ["Brooklyn"]
    assert result["u9"] == []


def test_resolve_no_duplicate_canonicals():
    units = [_make_unit("u10", people=["Grandma", "Rose", "Grandma Rose"])]
    result = resolve_unit_entity_ids(units, ENTITY_GRAPH)
    assert result["u10"].count("Grandma Rose") == 1


def test_resolve_empty_entity_graph():
    units = [_make_unit("u11", people=["Grandma"])]
    result = resolve_unit_entity_ids(units, ENTITY_GRAPH[:0])
    assert result["u11"] == []


# ── RAG: resolved_entity_ids stored in index ──────────────────────────────

def test_build_index_stores_resolved_entity_ids():
    rag = PersonaRAG()
    units = [
        {
            "content_first_person": "I grew up near Brooklyn.",
            "resolved_entity_ids": ["Brooklyn"],
        },
        {
            "content_first_person": "Grandma taught me to cook.",
            "resolved_entity_ids": ["Grandma Rose"],
        },
    ]
    rag.build_index_from_units(units)
    assert rag._units[0]["resolved_entity_ids"] == ["Brooklyn"]
    assert rag._units[1]["resolved_entity_ids"] == ["Grandma Rose"]


def test_build_index_missing_resolved_entity_ids_defaults_empty():
    rag = PersonaRAG()
    units = [{"content_first_person": "Some memory with no entities."}]
    rag.build_index_from_units(units)
    assert rag._units[0]["resolved_entity_ids"] == []


# ── RAG: score threshold (§9.7) ───────────────────────────────────────────

def test_score_threshold_constant_positive():
    assert 0.0 < _SCORE_THRESHOLD < 1.0


def test_entity_boost_constant_positive():
    assert 0.0 < _ENTITY_BOOST < 1.0


def test_retrieve_returns_empty_when_no_units():
    rag = PersonaRAG()
    assert rag.retrieve("hello") == []


def test_retrieve_keyword_fallback_no_threshold():
    """Keyword fallback (index=None) does not apply score threshold."""
    from unittest.mock import patch
    import config as _cfg
    rag = PersonaRAG()
    # index stays None — keyword path
    rag._units = [
        {"text": "completely unrelated nonsense", "resolved_entity_ids": []},
        {"text": "hello world today", "resolved_entity_ids": []},
    ]
    with patch.object(_cfg.settings, "force_mock_mode", True):
        result = rag.retrieve("hello world")
    assert len(result) >= 1


# ── RAG: listener_entity boost (§9.3) — keyword fallback ──────────────────

def test_retrieve_listener_entity_param_accepted_in_keyword_fallback():
    """listener_entity param must be accepted without error when index=None."""
    from unittest.mock import patch
    import config as _cfg
    rag = PersonaRAG()
    rag._units = [
        {"text": "memory about grandma cooking soup", "resolved_entity_ids": ["Grandma Rose"]},
        {"text": "memory about a sunny afternoon", "resolved_entity_ids": []},
    ]
    with patch.object(_cfg.settings, "force_mock_mode", True):
        result = rag.retrieve("cooking", listener_entity="Grandma Rose")
    assert isinstance(result, list)


# ── ListenerContext: entity_canonical field ───────────────────────────────

def test_listener_context_entity_canonical_defaults_none():
    ctx = ListenerContext(
        listener_user_id="u1",
        is_owner=False,
        allowed_modalities=ModalityConsent(),
    )
    assert ctx.entity_canonical is None


def test_listener_context_entity_canonical_set():
    ctx = ListenerContext(
        listener_user_id="u2",
        is_owner=False,
        allowed_modalities=ModalityConsent(),
        entity_canonical="Grandma Rose",
    )
    assert ctx.entity_canonical == "Grandma Rose"


def test_listener_context_owner_no_entity_canonical():
    ctx = ListenerContext(
        listener_user_id="u3",
        is_owner=True,
        allowed_modalities=ModalityConsent(),
    )
    assert ctx.entity_canonical is None
