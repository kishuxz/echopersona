from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MemorySource(BaseModel):
    modality: str  # video | text | letter | document | photo | audio
    question_category: str = ""
    question_text: str = ""
    source_question_id: str = ""   # stable question bank ID (e.g. q_origins_01) — §2.3 [add-004]
    source_type: str = "answer"    # "answer" | "correction" — §6/§7.1 [add-004]
    file_id: str = ""
    media_ref: str = ""            # storage:// URI — §2.3 [add-004]
    group_name: str = ""
    timestamp_range: tuple[float, float] = (0.0, 0.0)
    captured_at: str = ""          # ISO-8601 — §2.3 [add-004]


class MemoryAffect(BaseModel):
    emotion: str = ""
    valence: float = 0.0   # -1.0 to 1.0
    intensity: float = 0.0  # 0.0 to 1.0


class MemoryEntities(BaseModel):
    people: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    period: str = ""


class FidelityFlag(BaseModel):
    flagged_text: str
    reason: str


class MemoryUnit(BaseModel):
    unit_id: UUID = Field(default_factory=uuid4)
    user_id: str
    persona_id: str = ""           # §2.3 [add-004] — present in DB, now on model
    source: MemorySource
    content_first_person: str
    stance: str = ""
    affect: MemoryAffect = Field(default_factory=MemoryAffect)
    themes: list[str] = Field(default_factory=list)
    entities: MemoryEntities = Field(default_factory=MemoryEntities)
    version: int = 1               # §2.3 [add-004]
    supersedes: UUID | None = None # §2.3 [add-004] — unit_id this replaces (corrections §6/§7.1)
    verified: bool = False
    fidelity_flags: list[FidelityFlag] = Field(default_factory=list)
    fidelity_score: float = 1.0
    embedding: list[float] = Field(default_factory=list)


class MemoryUnitCreate(BaseModel):
    """Input for creating a memory unit before embedding is computed."""
    user_id: str
    source: MemorySource
    content_first_person: str
    stance: str = ""
    affect: MemoryAffect = Field(default_factory=MemoryAffect)
    themes: list[str] = Field(default_factory=list)
    entities: MemoryEntities = Field(default_factory=MemoryEntities)
