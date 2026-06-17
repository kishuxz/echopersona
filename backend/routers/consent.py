import logging

from fastapi import APIRouter, Depends, HTTPException

from middleware.auth import get_current_user
from models.consent import ConsentCreate, ConsentRecord, SuccessionCreate, SuccessionRecord
from services.consent import (
    get_active_consent_record,
    get_active_succession_record,
    write_consent_record,
    write_succession_record,
)
from services.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/personas", tags=["consent"])


@router.post("/{persona_id}/consent", response_model=ConsentRecord)
async def upsert_consent(
    persona_id: str,
    payload: ConsentCreate,
    user_id: str = Depends(get_current_user),
) -> ConsentRecord:
    db = get_db()
    record = await write_consent_record(db, persona_id, user_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Not found")
    return record


@router.get("/{persona_id}/consent", response_model=ConsentRecord)
async def read_consent(
    persona_id: str,
    user_id: str = Depends(get_current_user),
) -> ConsentRecord:
    db = get_db()
    record = await get_active_consent_record(db, persona_id, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Not found")
    return record


@router.post("/{persona_id}/succession", response_model=SuccessionRecord)
async def upsert_succession(
    persona_id: str,
    payload: SuccessionCreate,
    user_id: str = Depends(get_current_user),
) -> SuccessionRecord:
    db = get_db()
    record = await write_succession_record(db, persona_id, user_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Not found")
    return record


@router.get("/{persona_id}/succession", response_model=SuccessionRecord)
async def read_succession(
    persona_id: str,
    user_id: str = Depends(get_current_user),
) -> SuccessionRecord:
    db = get_db()
    record = await get_active_succession_record(db, persona_id, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Not found")
    return record
