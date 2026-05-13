import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from config import settings
from middleware.auth import get_current_user
from models.persona import Persona, PersonaCreate
from services import did, persona_store
from services.db import get_db
from services.rag import PERSONAS, RAG_INDICES, PersonaRAG
from services.tts import clone_voice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/persona", tags=["persona"])


async def _generate_idle_video(persona_id: str, avatar_url: str, voice_id: str | None, user_id: str) -> None:
    """Generate a short neutral D-ID video so the frontend has something to loop while idle."""
    try:
        url = await did.generate_talking_head("Hello.", voice_id, avatar_url)
        if url:
            await persona_store.update_idle_video_url(persona_id, user_id, url)
            if persona_id in PERSONAS:
                PERSONAS[persona_id].idle_video_url = url
            logger.info("Idle video stored for persona %s", persona_id)
    except Exception as exc:
        logger.error("Idle video generation failed for persona %s: %s", persona_id, exc)


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
    background_tasks: BackgroundTasks,
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

    if settings.did_api_key:
        background_tasks.add_task(_generate_idle_video, persona_id, avatar_url, persona.voice_id, user_id)

    return persona


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
