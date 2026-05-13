import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from middleware.auth import get_current_user
from models.persona import Persona, PersonaCreate
from services import persona_store
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
    logger.info(f"[AVATAR] upload request for persona {persona_id}, content_type={file.content_type}, filename={file.filename}")
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


@router.delete("/{persona_id}")
async def delete(
    persona_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    await persona_store.delete_persona(persona_id, user_id)
    PERSONAS.pop(persona_id, None)
    RAG_INDICES.pop(persona_id, None)
    return {"deleted": True}
