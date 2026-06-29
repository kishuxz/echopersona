import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from config import settings
from middleware.auth import get_current_user
from models.persona import Persona, PersonaCreate
from services import persona_store
from services.db import get_db
from services.rag import PERSONAS, RAG_INDICES, PersonaRAG
from services.tts import clone_voice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/persona", tags=["persona"])



@router.post("/create", response_model=Persona)
async def create(
    payload: PersonaCreate,
    user_id: str = Depends(get_current_user),
) -> Persona:
    persona = await persona_store.create_persona(user_id, payload)
    PERSONAS[persona.id] = persona
    rag = PersonaRAG()
    rag.build_index(payload.stories)
    RAG_INDICES[persona.id] = rag
    return persona


@router.get("/", response_model=list[Persona])
async def list_all(user_id: str = Depends(get_current_user)) -> list[Persona]:
    return await persona_store.list_personas(user_id)


@router.get("/{persona_id}", response_model=Persona)
async def get(
    persona_id: str,
    user_id: str = Depends(get_current_user),
) -> Persona:
    persona = await persona_store.get_persona(persona_id, user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.post("/{persona_id}/upload-voice", response_model=Persona)
async def upload_voice(
    persona_id: str,
    files: list[UploadFile] = File(...),
    user_id: str = Depends(get_current_user),
) -> Persona:
    persona = await persona_store.get_persona(persona_id, user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    voice_id = await clone_voice(persona_id, files)
    await persona_store.update_persona_voice(persona_id, user_id, voice_id)
    persona.voice_id = voice_id
    PERSONAS[persona_id] = persona
    return persona


@router.post("/{persona_id}/upload-avatar", response_model=Persona)
async def upload_avatar(
    persona_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
) -> Persona:
    logger.info("Avatar upload request for persona %s, content_type=%s, filename=%s", persona_id, file.content_type, file.filename)
    persona = await persona_store.get_persona(persona_id, user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    content_type = file.content_type or "image/jpeg"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    file_bytes = await file.read()
    avatar_url = await persona_store.upload_avatar_image(
        persona_id, user_id, file_bytes, content_type
    )
    persona.did_avatar_url = avatar_url
    PERSONAS[persona_id] = persona
    return persona


class ReadinessResponse(BaseModel):
    ready: bool
    status: str
    sources_done: int
    sources_total: int


@router.get("/{persona_id}/readiness", response_model=ReadinessResponse)
async def get_readiness(
    persona_id: str,
    user_id: str = Depends(get_current_user),
) -> ReadinessResponse:
    persona = await persona_store.get_persona(persona_id, user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    db = get_db()
    result = db.table("memory_sources").select("status").eq("persona_id", persona_id).execute()
    total = len(result.data)
    done = sum(1 for r in result.data if r["status"] == "done")
    return ReadinessResponse(
        ready=persona.readiness_status == "ready",
        status=persona.readiness_status,
        sources_done=done,
        sources_total=total,
    )


class SimliFacePayload(BaseModel):
    face_id: str


@router.post("/{persona_id}/simli-face", response_model=Persona)
async def set_simli_face(
    persona_id: str,
    payload: SimliFacePayload,
    user_id: str = Depends(get_current_user),
) -> Persona:
    persona = await persona_store.get_persona(persona_id, user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    await persona_store.update_persona_simli_face_id(persona_id, user_id, payload.face_id)
    persona.simli_face_id = payload.face_id
    PERSONAS[persona_id] = persona
    return persona


class PersonaUpdate(BaseModel):
    name: str | None = None
    stories: list[str] | None = None
    personality_traits: list[str] | None = None
    speaking_style: str | None = None
    tone: str | None = None
    avoid_phrases: list[str] | None = None
    answer_length_pref: str | None = None
    relationship_tone: dict | None = None


@router.patch("/{persona_id}", response_model=Persona)
async def update_persona(
    persona_id: str,
    payload: PersonaUpdate,
    user_id: str = Depends(get_current_user),
) -> Persona:
    persona = await persona_store.get_persona(persona_id, user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    updates = payload.model_dump(exclude_none=True)
    if updates:
        db = get_db()
        db.table("personas").update(updates).eq("id", persona_id).eq("user_id", user_id).execute()
        PERSONAS.pop(persona_id, None)
        RAG_INDICES.pop(persona_id, None)
    return await persona_store.get_persona(persona_id, user_id)


@router.delete("/{persona_id}")
async def delete(
    persona_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    await persona_store.delete_persona(persona_id, user_id)
    PERSONAS.pop(persona_id, None)
    RAG_INDICES.pop(persona_id, None)
    return {"deleted": True}
