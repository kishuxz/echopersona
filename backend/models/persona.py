from datetime import datetime

from pydantic import BaseModel, Field


class PersonaCreate(BaseModel):
    name: str
    stories: list[str] = Field(default_factory=list)
    personality_traits: list[str] = Field(default_factory=list)
    speaking_style: str = ""


class Persona(PersonaCreate):
    id: str
    user_id: str
    voice_id: str | None = None
    did_avatar_url: str | None = None
    idle_video_url: str | None = None
    simli_face_id: str | None = None
    # Stage 3: resolved entity graph — list of {canonical, type, aliases, description}
    entity_graph: list[dict] = Field(default_factory=list)
    # Stage 4: characteristic speech excerpts for style conditioning
    style_exemplars: list[str] = Field(default_factory=list)
    # Stage 4: structured voice/speech style card (migration 008)
    voice_card: dict = Field(default_factory=dict)
    # Stage 4B: structured identity card — WHO the persona IS (migration 010)
    identity_card: dict = Field(default_factory=dict)
    # Phase 2 style card fields (migration 007_persona_style_card)
    tone: str = ""
    avoid_phrases: list[str] = Field(default_factory=list)
    answer_length_pref: str = ""
    relationship_tone: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    readiness_status: str = "pending"
