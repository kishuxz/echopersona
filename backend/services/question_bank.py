"""Question bank loader — PERSONA_SPEC.md §5.

Loads and validates the static YAML bank at data/question_bank.yaml.
No LLM calls. No I/O beyond the initial file read (cached after first load).

Public API:
    get_question_bank()           -> list[QuestionEntry]  (bank in YAML order)
    get_question(qid)             -> QuestionEntry | None
    get_steering_bank()           -> dict[str, str]       (steer_id -> template)
    questions_by_category(cat)    -> list[QuestionEntry]  (sorted by order)
    questions_in_creation_order() -> list[QuestionEntry]  (§5.1 category order)
    CATEGORY_ORDER                -> list[str]            (§5.1 category sequence)
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError, model_validator

_BANK_PATH = Path(__file__).parent.parent / "data" / "question_bank.yaml"

_VALID_GOOD_WHEN = {"shallow", "missing_signal", "specific_thread"}
_VALID_MODALITY = {"text", "video_audio"}
_VALID_STEERING_IDS = {"refocus", "wrap_up", "too_short", "sensitive_ok"}


class Probe(BaseModel):
    id: str
    prompt: str
    good_when: Literal["shallow", "missing_signal", "specific_thread"]

    @model_validator(mode="after")
    def _probe_id_nonempty(self) -> "Probe":
        if not self.id.strip():
            raise ValueError("probe id must not be empty")
        return self


class QuestionEntry(BaseModel):
    id: str
    category: str
    order: int
    modality: Literal["text", "video_audio"]
    required: bool
    prompt: str
    intent: str
    signals: list[str]
    max_followups: int
    probes: list[Probe]

    @model_validator(mode="after")
    def _validate_probes(self) -> "QuestionEntry":
        if len(self.probes) > self.max_followups:
            raise ValueError(
                f"{self.id}: probe count ({len(self.probes)}) exceeds max_followups ({self.max_followups})"
            )
        seen_probe_ids: set[str] = set()
        for p in self.probes:
            if not p.id.startswith(self.id + "_"):
                raise ValueError(
                    f"probe {p.id!r} must be namespaced under question {self.id!r}"
                )
            if p.id in seen_probe_ids:
                raise ValueError(f"duplicate probe id {p.id!r} in question {self.id!r}")
            seen_probe_ids.add(p.id)
        return self

    def probe_by_id(self, probe_id: str) -> Probe | None:
        return next((p for p in self.probes if p.id == probe_id), None)


class QuestionBank(BaseModel):
    questions: list[QuestionEntry]
    steering: dict[str, str]

    @model_validator(mode="after")
    def _validate_ids_unique(self) -> "QuestionBank":
        seen: set[str] = set()
        for q in self.questions:
            if q.id in seen:
                raise ValueError(f"duplicate question id {q.id!r}")
            seen.add(q.id)
        return self


def _load_raw() -> QuestionBank:
    with open(_BANK_PATH, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    questions_raw = raw.get("questions") or []
    steering_raw = raw.get("steering") or {}

    try:
        bank = QuestionBank(questions=questions_raw, steering=steering_raw)
    except ValidationError as exc:
        raise RuntimeError(f"question_bank.yaml failed validation:\n{exc}") from exc

    return bank


@functools.lru_cache(maxsize=1)
def _bank() -> QuestionBank:
    return _load_raw()


def get_question_bank() -> list[QuestionEntry]:
    """All questions in category/order sort (creation order per §5.1)."""
    return list(_bank().questions)


def get_question(qid: str) -> QuestionEntry | None:
    return next((q for q in _bank().questions if q.id == qid), None)


def get_steering_bank() -> dict[str, str]:
    return dict(_bank().steering)


def questions_by_category(category: str) -> list[QuestionEntry]:
    return sorted(
        [q for q in _bank().questions if q.category == category],
        key=lambda q: q.order,
    )


# §5.1 Memory Lane category sequence — drives creation order
CATEGORY_ORDER: list[str] = [
    "origins", "family", "coming_of_age", "love", "work",
    "beliefs", "texture", "hardship", "places", "legacy", "_consent",
]


def _category_sort_key(q: QuestionEntry) -> tuple[int, int]:
    try:
        idx = CATEGORY_ORDER.index(q.category)
    except ValueError:
        idx = len(CATEGORY_ORDER)  # unknown categories sort after all known ones
    return (idx, q.order)


@functools.lru_cache(maxsize=1)
def questions_in_creation_order() -> list[QuestionEntry]:
    """All questions sorted by §5.1 category order, then by `order` within each category."""
    return sorted(get_question_bank(), key=_category_sort_key)
