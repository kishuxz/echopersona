from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ModalityConsent(BaseModel):
    voice_clone: bool = False
    video_avatar: bool = False
    text_twin: bool = True


class ConsentRights(BaseModel):
    subject_may_delete: bool = True
    subject_may_review: bool = True


class ConsentCreate(BaseModel):
    modality_consent: ModalityConsent = Field(default_factory=ModalityConsent)
    rights: ConsentRights = Field(default_factory=ConsentRights)
    policy_version: str = "1"
    affirmation_media_ref: str | None = None


class ConsentRecord(ConsentCreate):
    id: str
    persona_id: str
    subject_user_id: str
    captured_at: datetime
    consent_version: int
    status: Literal["active", "superseded", "revoked"]
    ended_at: datetime | None = None
    supersedes: str | None = None


class SuccessionBeneficiary(BaseModel):
    user_id: str
    relationship: str
    address_term: str = ""
    scope: Literal["full", "curated"]
    activation_trigger: Literal["immediate", "posthumous_verified"]
    release_messages: list[str] = Field(default_factory=list)
    closeness_level: int | None = Field(default=None, ge=1, le=5)
    greeting_style: str | None = None


class SuccessionCreate(BaseModel):
    beneficiaries: list[SuccessionBeneficiary] = Field(default_factory=list)


class SuccessionRecord(SuccessionCreate):
    id: str
    persona_id: str
    subject_user_id: str
    captured_at: datetime
    status: Literal["active", "superseded", "revoked"]
    ended_at: datetime | None = None
    supersedes: str | None = None


class ListenerContext(BaseModel):
    """Resolved access context for a live-session participant.

    Built at WebSocket connect time from consent_records + succession_records.
    Never inferred — always authenticated from DB records.
    """
    listener_user_id: str
    is_owner: bool
    relationship: str | None = None
    address_term: str | None = None
    scope: Literal["full", "curated"] | None = None
    allowed_modalities: ModalityConsent
    closeness_level: int | None = None
    greeting_style: str | None = None
    entity_canonical: str | None = None  # §9.3 — from persona_relationships table
