from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr


class InviteCreate(BaseModel):
    email: EmailStr
    relationship: str = ""
    entity_canonical: str = ""
    address_term: str = ""


class InviteRecord(BaseModel):
    id: str
    persona_id: str
    email: str
    relationship: str
    status: Literal["pending", "accepted", "revoked"]
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    created_at: datetime


class AcceptInviteRequest(BaseModel):
    token: str


class AcceptInviteResponse(BaseModel):
    persona_id: str
    relationship: str
    entity_canonical: str
