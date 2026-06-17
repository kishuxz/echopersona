"""Tests for the answer evaluator (build step 3, PERSONA_SPEC.md §4).

Tests the pure helpers directly and the async evaluate_next_action wrapper
with a mocked _call_evaluator_raw. No Redis, no DB, no real Groq calls.
asyncio.run() drives async cases — no pytest-asyncio needed.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from services.creation import (
    CreationSession,
    SHORT_ANSWER_THRESHOLD,
    _build_evaluator_input,
    _update_coverage,
    _validate_evaluator_output,
    evaluate_next_action,
)
from services.question_bank import Probe, QuestionEntry, get_question


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _session(**kw) -> CreationSession:
    return CreationSession(persona_id="p1", user_id="u1", **kw)


def _q(qid: str) -> QuestionEntry:
    q = get_question(qid)
    assert q is not None, f"question {qid!r} not found in bank"
    return q


def _advance_raw(**overrides) -> dict:
    base = {
        "answered": True,
        "answer_quality": {
            "depth": "adequate",
            "on_topic": True,
            "multi_topic": False,
            "topics_touched": ["hometown"],
            "signals_present": ["affect"],
        },
        "next_action": "advance",
        "probe_id": None,
        "steer_id": None,
        "skip_reason": None,
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def _probe_raw(probe_id: str, confidence: float = 0.8) -> dict:
    return {
        "answered": True,
        "answer_quality": {
            "depth": "shallow",
            "on_topic": True,
            "multi_topic": False,
            "topics_touched": ["hometown"],
            "signals_present": [],
        },
        "next_action": "ask_probe",
        "probe_id": probe_id,
        "steer_id": None,
        "skip_reason": None,
        "confidence": confidence,
    }


def _steer_raw(steer_id: str = "refocus") -> dict:
    return {
        "answered": False,
        "answer_quality": {
            "depth": "shallow",
            "on_topic": False,
            "multi_topic": False,
            "topics_touched": [],
            "signals_present": [],
        },
        "next_action": "steer",
        "probe_id": None,
        "steer_id": steer_id,
        "skip_reason": None,
        "confidence": 0.85,
    }


# ── _validate_evaluator_output — unit tests (pure, synchronous) ───────────────


def test_validate_valid_advance():
    q = _q("q_origins_01")
    s = _session()
    result = _validate_evaluator_output(_advance_raw(), q, s)
    assert result == {"next_action": "advance", "skip_reason": None}


def test_validate_valid_probe():
    q = _q("q_origins_01")
    s = _session()
    result = _validate_evaluator_output(_probe_raw("q_origins_01_p1"), q, s)
    assert result == {"next_action": "ask_probe", "probe_id": "q_origins_01_p1"}


def test_validate_probe_id_not_in_prepared_probes_returns_none():
    q = _q("q_origins_01")
    s = _session()
    raw = _probe_raw("q_INJECTED_evil_probe")
    assert _validate_evaluator_output(raw, q, s) is None


def test_validate_unknown_next_action_returns_none():
    q = _q("q_origins_01")
    s = _session()
    raw = _advance_raw(next_action="invent_question")
    assert _validate_evaluator_output(raw, q, s) is None


def test_validate_missing_next_action_returns_none():
    q = _q("q_origins_01")
    s = _session()
    assert _validate_evaluator_output({}, q, s) is None


def test_validate_cap_reached_forces_advance():
    q = _q("q_origins_01")  # max_followups=2
    s = _session(followups_used_this_question=2)
    raw = _probe_raw("q_origins_01_p1")
    result = _validate_evaluator_output(raw, q, s)
    assert result == {"next_action": "advance", "skip_reason": "capped"}


def test_validate_all_signals_saturated_overrides_to_advance():
    q = _q("q_origins_01")  # signals: [affect, voice_texture, themes]
    coverage = {"affect": "saturated", "voice_texture": "saturated", "themes": "saturated"}
    s = _session(signal_coverage=coverage)
    raw = _probe_raw("q_origins_01_p1")
    result = _validate_evaluator_output(raw, q, s)
    assert result == {"next_action": "advance", "skip_reason": "saturated"}


def test_validate_confidence_below_half_forces_advance():
    q = _q("q_origins_01")
    s = _session()
    raw = _probe_raw("q_origins_01_p1", confidence=0.4)
    result = _validate_evaluator_output(raw, q, s)
    assert result == {"next_action": "advance", "skip_reason": "low_value"}


def test_validate_confidence_at_threshold_allows_probe():
    q = _q("q_origins_01")
    s = _session()
    raw = _probe_raw("q_origins_01_p1", confidence=0.5)
    result = _validate_evaluator_output(raw, q, s)
    assert result == {"next_action": "ask_probe", "probe_id": "q_origins_01_p1"}


def test_validate_valid_steer():
    q = _q("q_origins_01")
    s = _session()
    result = _validate_evaluator_output(_steer_raw("refocus"), q, s)
    assert result == {"next_action": "steer", "steer_id": "refocus"}


def test_validate_invalid_steer_id_returns_none():
    q = _q("q_origins_01")
    s = _session()
    result = _validate_evaluator_output(_steer_raw("MAKE_UP_A_STEER"), q, s)
    assert result is None


def test_validate_advance_normalises_string_null_skip_reason():
    q = _q("q_origins_01")
    s = _session()
    raw = _advance_raw(skip_reason="null")
    result = _validate_evaluator_output(raw, q, s)
    assert result == {"next_action": "advance", "skip_reason": None}


def test_validate_advance_unknown_skip_reason_becomes_none():
    q = _q("q_origins_01")
    s = _session()
    raw = _advance_raw(skip_reason="INVENTED_REASON")
    result = _validate_evaluator_output(raw, q, s)
    assert result == {"next_action": "advance", "skip_reason": None}


# ── _update_coverage — unit tests (pure, synchronous) ────────────────────────


def test_update_coverage_none_to_partial():
    s = _session()
    new_s = _update_coverage(s, signals_present=["affect"], topics_touched=[])
    assert new_s.signal_coverage["affect"] == "partial"


def test_update_coverage_partial_to_saturated():
    s = _session(signal_coverage={"affect": "partial"})
    new_s = _update_coverage(s, signals_present=["affect"], topics_touched=[])
    assert new_s.signal_coverage["affect"] == "saturated"


def test_update_coverage_saturated_stays_saturated():
    s = _session(signal_coverage={"affect": "saturated"})
    new_s = _update_coverage(s, signals_present=["affect"], topics_touched=[])
    assert new_s.signal_coverage["affect"] == "saturated"


def test_update_coverage_accumulates_topics():
    s = _session(topics_well_covered=["family"])
    new_s = _update_coverage(s, signals_present=[], topics_touched=["hometown", "family"])
    assert "hometown" in new_s.topics_well_covered
    assert new_s.topics_well_covered.count("family") == 1  # no duplicate


def test_update_coverage_does_not_mutate_input():
    s = _session()
    _update_coverage(s, signals_present=["affect"], topics_touched=["foo"])
    assert s.signal_coverage == {}
    assert s.topics_well_covered == []


# ── _build_evaluator_input — unit tests (pure, synchronous) ──────────────────


def test_build_evaluator_input_shape():
    q = _q("q_origins_01")
    s = _session(
        followups_used_this_question=1,
        signal_coverage={"affect": "partial", "voice_texture": "saturated"},
        topics_well_covered=["hometown"],
    )
    inp = _build_evaluator_input(q, "I grew up near a big temple.", s)

    assert inp["question"]["id"] == "q_origins_01"
    assert inp["answer_text"] == "I grew up near a big temple."
    assert inp["session_state"]["followups_used_this_question"] == 1
    assert inp["session_state"]["max_followups"] == q.max_followups
    assert inp["session_state"]["signal_coverage"] == {
        "affect": "partial",
        "voice_texture": "saturated",
    }
    assert inp["session_state"]["topics_well_covered"] == ["hometown"]
    assert all("id" in p for p in inp["prepared_probes"])


def test_build_evaluator_input_omits_none_signals():
    q = _q("q_origins_01")
    s = _session(signal_coverage={"affect": "none"})
    inp = _build_evaluator_input(q, "answer", s)
    assert "affect" not in inp["session_state"]["signal_coverage"]


# ── evaluate_next_action — integration tests (async via asyncio.run) ──────────


def test_evaluate_valid_advance_flows_through():
    q = _q("q_origins_01")
    s = _session(current_question_id=q.id)
    raw = _advance_raw()

    with patch("services.creation._call_evaluator_raw", new_callable=AsyncMock, return_value=raw):
        new_s, action = asyncio.run(evaluate_next_action(s, q, "A rich answer about my hometown."))

    assert action["next_action"] == "advance"
    assert new_s.signal_coverage.get("affect") == "partial"
    assert "hometown" in new_s.topics_well_covered


def test_evaluate_valid_probe_flows_through():
    q = _q("q_origins_01")
    s = _session(current_question_id=q.id)
    raw = _probe_raw("q_origins_01_p1", confidence=0.85)

    with patch("services.creation._call_evaluator_raw", new_callable=AsyncMock, return_value=raw):
        new_s, action = asyncio.run(evaluate_next_action(s, q, "In Madurai."))

    assert action["next_action"] == "ask_probe"
    assert action["probe_id"] == "q_origins_01_p1"


def test_evaluate_invalid_json_falls_back_to_deterministic():
    q = _q("q_origins_01")
    s = _session(current_question_id=q.id)

    with patch(
        "services.creation._call_evaluator_raw",
        new_callable=AsyncMock,
        side_effect=ValueError("bad JSON"),
    ):
        new_s, action = asyncio.run(evaluate_next_action(s, q, "Short."))

    # deterministic fallback: short first answer → ask_probe
    assert action["next_action"] == "ask_probe"
    assert action["probe_id"] == "q_origins_01_p1"


def test_evaluate_probe_id_injection_falls_back_to_deterministic():
    q = _q("q_origins_01")
    s = _session(current_question_id=q.id)
    raw = _probe_raw("INJECTED_EVIL_PROBE")

    with patch("services.creation._call_evaluator_raw", new_callable=AsyncMock, return_value=raw):
        new_s, action = asyncio.run(
            evaluate_next_action(s, q, "Short answer so fallback probes.")
        )

    # validation returns None → falls back → short answer triggers deterministic probe
    assert action["next_action"] == "ask_probe"
    assert action["probe_id"] == "q_origins_01_p1"


def test_evaluate_cap_reached_forces_advance():
    q = _q("q_origins_01")  # max_followups=2
    s = _session(current_question_id=q.id, followups_used_this_question=2)
    raw = _probe_raw("q_origins_01_p1")

    with patch("services.creation._call_evaluator_raw", new_callable=AsyncMock, return_value=raw):
        new_s, action = asyncio.run(evaluate_next_action(s, q, "Short."))

    assert action["next_action"] == "advance"
    assert action.get("skip_reason") == "capped"


def test_evaluate_off_topic_steer():
    q = _q("q_origins_01")
    s = _session(current_question_id=q.id)
    raw = _steer_raw("refocus")

    with patch("services.creation._call_evaluator_raw", new_callable=AsyncMock, return_value=raw):
        new_s, action = asyncio.run(evaluate_next_action(s, q, "Let me talk about my work instead."))

    assert action["next_action"] == "steer"
    assert action["steer_id"] == "refocus"


def test_evaluate_groq_timeout_falls_back():
    q = _q("q_origins_01")
    s = _session(current_question_id=q.id)

    with patch(
        "services.creation._call_evaluator_raw",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("timeout"),
    ):
        new_s, action = asyncio.run(
            evaluate_next_action(s, q, "x" * SHORT_ANSWER_THRESHOLD)
        )

    # long answer → deterministic fallback → advance
    assert action["next_action"] == "advance"


def test_evaluate_signal_coverage_accumulates_across_calls():
    q = _q("q_origins_01")
    s = _session(current_question_id=q.id, signal_coverage={"affect": "partial"})
    raw = _advance_raw()

    with patch("services.creation._call_evaluator_raw", new_callable=AsyncMock, return_value=raw):
        new_s, _ = asyncio.run(evaluate_next_action(s, q, "A rich answer."))

    # "affect" was partial, evaluator reports it again → saturated
    assert new_s.signal_coverage["affect"] == "saturated"
