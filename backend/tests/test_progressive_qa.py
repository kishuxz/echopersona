"""Tests for Slice 2: Progressive Q&A — bank size, category tracking, NextStep enrichment."""
import pytest

from services.creation import (
    CreationSession,
    apply_action,
    select_next_question,
)
from services.question_bank import (
    CATEGORY_ORDER,
    get_question,
    get_question_bank,
    questions_by_category,
    questions_in_creation_order,
)


def _session(**kw) -> CreationSession:
    return CreationSession(persona_id="p1", user_id="u1", **kw)


def _q(qid: str):
    q = get_question(qid)
    assert q is not None, f"question {qid!r} not found in bank"
    return q


# ── Bank size ─────────────────────────────────────────────────────────────────


def test_bank_has_at_least_10_questions():
    """Min-10 finish threshold requires the bank to have at least 10 questions."""
    assert len(get_question_bank()) >= 10


def test_coming_of_age_category_has_questions():
    qs = questions_by_category("coming_of_age")
    assert len(qs) >= 1, "coming_of_age was empty; Slice 2 should have added questions"


def test_every_active_category_has_at_least_2_questions():
    active = [c for c in CATEGORY_ORDER if c != "_consent"]
    for cat in active:
        qs = questions_by_category(cat)
        assert len(qs) >= 2, f"category {cat!r} has only {len(qs)} question(s)"


def test_all_probe_ids_namespaced_under_parent():
    for q in get_question_bank():
        for probe in q.probes:
            assert probe.id.startswith(q.id + "_"), (
                f"probe {probe.id!r} not namespaced under {q.id!r}"
            )


def test_no_duplicate_question_ids():
    ids = [q.id for q in get_question_bank()]
    assert len(ids) == len(set(ids)), "duplicate question ids in bank"


# ── answers_per_category tracking ─────────────────────────────────────────────


def test_answers_per_category_initialises_empty():
    session = _session()
    assert session.answers_per_category == {}


def test_advance_increments_answers_per_category():
    ordered = questions_in_creation_order()
    q = ordered[0]
    session = _session(current_question_id=q.id)
    new_session, _ = apply_action(session, q, {"next_action": "advance"})
    assert new_session.answers_per_category.get(q.category, 0) == 1


def test_multiple_advances_accumulate_per_category():
    ordered = questions_in_creation_order()
    # Find two questions in the same category
    first = ordered[0]
    same_cat = [q for q in ordered if q.category == first.category]
    if len(same_cat) < 2:
        pytest.skip(f"need at least 2 questions in {first.category!r}")

    q1, q2 = same_cat[0], same_cat[1]
    session = _session(current_question_id=q1.id)
    session, _ = apply_action(session, q1, {"next_action": "advance"})
    assert session.answers_per_category.get(q1.category, 0) == 1

    session = session.model_copy(update={"current_question_id": q2.id})
    session, _ = apply_action(session, q2, {"next_action": "advance"})
    assert session.answers_per_category.get(q2.category, 0) == 2


def test_probe_does_not_increment_answers_per_category():
    q = _q("q_origins_01")
    session = _session(current_question_id=q.id)
    new_session, _ = apply_action(
        session, q, {"next_action": "ask_probe", "probe_id": "q_origins_01_p1"}
    )
    assert new_session.answers_per_category == {}


def test_steer_does_not_increment_answers_per_category():
    q = _q("q_beliefs_01")
    session = _session(current_question_id=q.id)
    new_session, _ = apply_action(
        session, q, {"next_action": "steer", "steer_id": "too_short"}
    )
    assert new_session.answers_per_category == {}


def test_advance_preserves_existing_category_counts():
    q_origins = _q("q_origins_01")
    q_family = _q("q_family_01")
    # Simulate having answered one origins already
    session = _session(
        current_question_id=q_family.id,
        completed_question_ids=[q_origins.id],
        answers_per_category={"origins": 1},
    )
    new_session, _ = apply_action(session, q_family, {"next_action": "advance"})
    assert new_session.answers_per_category.get("origins", 0) == 1
    assert new_session.answers_per_category.get("family", 0) == 1


# ── question_category in NextStep ────────────────────────────────────────────


def test_advance_next_step_has_question_category():
    ordered = questions_in_creation_order()
    q0, q1 = ordered[0], ordered[1]
    session = _session(current_question_id=q0.id)
    _, step = apply_action(session, q0, {"next_action": "advance"})
    assert step.question_category == q1.category


def test_ask_probe_next_step_has_current_question_category():
    q = _q("q_origins_01")
    session = _session(current_question_id=q.id)
    _, step = apply_action(
        session, q, {"next_action": "ask_probe", "probe_id": "q_origins_01_p1"}
    )
    assert step.question_category == q.category


def test_steer_next_step_has_current_question_category():
    q = _q("q_beliefs_01")
    session = _session(current_question_id=q.id)
    _, step = apply_action(session, q, {"next_action": "steer", "steer_id": "refocus"})
    assert step.question_category == q.category


def test_done_step_has_no_question_category():
    all_ids = [q.id for q in get_question_bank()]
    last_q = get_question(all_ids[-1])
    session = _session(
        current_question_id=last_q.id,
        completed_question_ids=all_ids[:-1],
    )
    _, step = apply_action(session, last_q, {"next_action": "advance"})
    assert step.action == "done"
    assert step.question_category is None


# ── Category ordering ─────────────────────────────────────────────────────────


def test_coming_of_age_sorted_between_family_and_love():
    order_cats = [q.category for q in questions_in_creation_order()]
    # Remove duplicates while preserving order
    seen = []
    for c in order_cats:
        if c not in seen:
            seen.append(c)
    assert "family" in seen
    assert "coming_of_age" in seen
    assert "love" in seen
    fam_idx = seen.index("family")
    coa_idx = seen.index("coming_of_age")
    love_idx = seen.index("love")
    assert fam_idx < coa_idx < love_idx, (
        "coming_of_age should appear between family and love in creation order"
    )
