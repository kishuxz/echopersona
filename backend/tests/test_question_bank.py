"""Tests for the question bank loader (build step 1, §5.3)."""
import pytest

from services.question_bank import (
    QuestionEntry,
    get_question,
    get_question_bank,
    get_steering_bank,
    questions_by_category,
)


def test_bank_loads_and_is_nonempty():
    bank = get_question_bank()
    assert len(bank) > 0, "question bank must have at least one question"


def test_all_entries_are_question_entries():
    for q in get_question_bank():
        assert isinstance(q, QuestionEntry)


def test_required_fields_present():
    for q in get_question_bank():
        assert q.id, f"question missing id: {q}"
        assert q.category, f"{q.id}: missing category"
        assert q.prompt, f"{q.id}: missing prompt"
        assert q.intent, f"{q.id}: missing intent"
        assert q.signals, f"{q.id}: signals must not be empty"
        assert q.max_followups >= 0, f"{q.id}: max_followups must be >= 0"


def test_probe_ids_are_namespaced():
    for q in get_question_bank():
        for p in q.probes:
            assert p.id.startswith(q.id + "_"), (
                f"probe {p.id!r} must start with {q.id + '_'!r}"
            )


def test_probe_count_within_max_followups():
    for q in get_question_bank():
        assert len(q.probes) <= q.max_followups, (
            f"{q.id}: {len(q.probes)} probes > max_followups {q.max_followups}"
        )


def test_modality_values():
    valid = {"text", "video_audio"}
    for q in get_question_bank():
        assert q.modality in valid, f"{q.id}: invalid modality {q.modality!r}"


def test_good_when_values():
    valid = {"shallow", "missing_signal", "specific_thread"}
    for q in get_question_bank():
        for p in q.probes:
            assert p.good_when in valid, (
                f"{p.id}: invalid good_when {p.good_when!r}"
            )


def test_question_ids_unique():
    ids = [q.id for q in get_question_bank()]
    assert len(ids) == len(set(ids)), "duplicate question ids detected"


def test_legacy_01_is_required():
    q = get_question("q_legacy_01")
    assert q is not None, "q_legacy_01 must exist"
    assert q.required is True, "q_legacy_01 must be required=true"


def test_get_question_known():
    q = get_question("q_origins_01")
    assert q is not None
    assert q.category == "origins"
    assert q.modality == "video_audio"


def test_get_question_unknown_returns_none():
    assert get_question("q_does_not_exist") is None


def test_questions_by_category_sorted():
    origins = questions_by_category("origins")
    assert len(origins) >= 2
    orders = [q.order for q in origins]
    assert orders == sorted(orders), "questions_by_category must return sorted by order"


def test_steering_bank_has_required_ids():
    steering = get_steering_bank()
    for sid in ("refocus", "wrap_up", "too_short", "sensitive_ok"):
        assert sid in steering, f"steering bank missing {sid!r}"
        assert steering[sid], f"steering bank {sid!r} must not be empty"


def test_probe_by_id():
    q = get_question("q_family_01")
    assert q is not None
    p = q.probe_by_id("q_family_01_p1")
    assert p is not None
    assert p.good_when == "missing_signal"

    assert q.probe_by_id("q_family_01_pX") is None
