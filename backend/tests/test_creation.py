"""Tests for the creation state machine (build step 2, PERSONA_SPEC.md §3).

Tests only the pure, I/O-free functions: select_next_question,
deterministic_next_action, apply_action.  No Redis, no DB, no LLM.
"""
import pytest

from services.creation import (
    CreationSession,
    NextStep,
    SHORT_ANSWER_THRESHOLD,
    apply_action,
    deterministic_next_action,
    select_next_question,
)
from services.question_bank import (
    QuestionEntry,
    Probe,
    get_question,
    get_question_bank,
    questions_in_creation_order,
)


def _session(**kw) -> CreationSession:
    return CreationSession(persona_id="p1", user_id="u1", **kw)


def _q(qid: str) -> QuestionEntry:
    q = get_question(qid)
    assert q is not None, f"question {qid!r} not found in bank"
    return q


# ── select_next_question ──────────────────────────────────────────────────────


def test_empty_session_returns_first_question():
    first = questions_in_creation_order()[0]
    assert select_next_question(_session()) == first


def test_completed_question_is_skipped():
    ordered = questions_in_creation_order()
    session = _session(completed_question_ids=[ordered[0].id])
    assert select_next_question(session) == ordered[1]


def test_returns_none_when_all_done():
    all_ids = [q.id for q in get_question_bank()]
    assert select_next_question(_session(completed_question_ids=all_ids)) is None


def test_required_question_is_present_in_creation_order():
    ids = [q.id for q in questions_in_creation_order()]
    assert "q_legacy_01" in ids


def test_creation_order_puts_origins_before_legacy():
    ordered = questions_in_creation_order()
    ids = [q.id for q in ordered]
    assert ids.index("q_origins_01") < ids.index("q_legacy_01")


# ── deterministic_next_action ─────────────────────────────────────────────────


def test_short_first_answer_triggers_probe():
    q = _q("q_origins_01")
    result = deterministic_next_action(0, q.max_followups, "Yes.", q)
    assert result["next_action"] == "ask_probe"
    assert result["probe_id"] == "q_origins_01_p1"


def test_long_first_answer_advances():
    q = _q("q_origins_01")
    result = deterministic_next_action(0, q.max_followups, "x" * SHORT_ANSWER_THRESHOLD, q)
    assert result["next_action"] == "advance"


def test_at_max_followups_always_advances():
    q = _q("q_family_01")
    result = deterministic_next_action(q.max_followups, q.max_followups, "Short.", q)
    assert result["next_action"] == "advance"


def test_second_followup_with_short_answer_advances():
    q = _q("q_origins_01")
    result = deterministic_next_action(1, q.max_followups, "Yes.", q)
    assert result["next_action"] == "advance"


def test_question_with_no_probes_always_advances():
    q = QuestionEntry(
        id="q_noprobe_01", category="work", order=99, modality="text",
        required=False, prompt="test", intent="test",
        signals=["themes"], max_followups=0, probes=[],
    )
    assert deterministic_next_action(0, 0, "Short.", q)["next_action"] == "advance"


# ── apply_action ──────────────────────────────────────────────────────────────


def test_advance_marks_question_complete_and_moves_to_next():
    ordered = questions_in_creation_order()
    q0, q1 = ordered[0], ordered[1]
    session = _session(current_question_id=q0.id)
    new_session, step = apply_action(session, q0, {"next_action": "advance"})

    assert q0.id in new_session.completed_question_ids
    assert new_session.followups_used_this_question == 0
    assert new_session.current_probe_id is None
    assert step.action == "advance"
    assert step.question_id == q1.id
    assert step.question_prompt == q1.prompt


def test_advance_on_last_question_returns_done():
    all_ids = [q.id for q in get_question_bank()]
    last_q = get_question(all_ids[-1])
    session = _session(
        current_question_id=last_q.id,
        completed_question_ids=all_ids[:-1],
    )
    new_session, step = apply_action(session, last_q, {"next_action": "advance"})
    assert step.action == "done"
    assert new_session.current_question_id is None


def test_ask_probe_sets_probe_and_increments_followups():
    q = _q("q_origins_01")
    session = _session(current_question_id=q.id, followups_used_this_question=0)
    new_session, step = apply_action(
        session, q, {"next_action": "ask_probe", "probe_id": "q_origins_01_p1"}
    )
    assert new_session.current_probe_id == "q_origins_01_p1"
    assert new_session.followups_used_this_question == 1
    assert step.action == "ask_probe"
    assert step.probe_id == "q_origins_01_p1"
    assert step.prompt is not None  # probe's own prompt text


def test_steer_does_not_advance_question():
    q = _q("q_beliefs_01")
    session = _session(current_question_id=q.id)
    new_session, step = apply_action(
        session, q, {"next_action": "steer", "steer_id": "too_short"}
    )
    assert new_session.current_question_id == q.id
    assert q.id not in new_session.completed_question_ids
    assert step.action == "steer"
    assert step.prompt is not None
    assert "time" in step.prompt.lower()  # "Take your time…"


def test_steer_refocus_fills_topic_placeholder():
    q = _q("q_origins_01")
    session = _session(current_question_id=q.id)
    _, step = apply_action(session, q, {"next_action": "steer", "steer_id": "refocus"})
    assert "{topic}" not in step.prompt
    assert q.category in step.prompt


def test_apply_action_does_not_mutate_input_session():
    q = _q("q_origins_01")
    original = _session(current_question_id=q.id)
    new_session, _ = apply_action(original, q, {"next_action": "advance"})
    assert q.id not in original.completed_question_ids
    assert q.id in new_session.completed_question_ids


def test_probe_then_advance_clears_probe_state():
    q = _q("q_origins_01")
    # Start on a probe
    session = _session(
        current_question_id=q.id,
        current_probe_id="q_origins_01_p1",
        followups_used_this_question=1,
    )
    new_session, step = apply_action(session, q, {"next_action": "advance"})
    assert new_session.current_probe_id is None
    assert new_session.followups_used_this_question == 0
    assert q.id in new_session.completed_question_ids
