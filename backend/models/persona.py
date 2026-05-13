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
    simli_face_id: str | None = None
    created_at: datetime | None = None
