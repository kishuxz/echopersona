import logging
import uuid

from models.persona import Persona, PersonaCreate
from services.db import get_db

logger = logging.getLogger(__name__)

AVATAR_BUCKET = "avatars"


async def upload_avatar_image(
    persona_id: str, user_id: str, file_bytes: bytes, content_type: str
) -> str:
    """Upload avatar image to Supabase Storage and return the public URL."""
    db = get_db()
    ext = content_type.split("/")[-1] if "/" in content_type else "jpg"
    path = f"{user_id}/{persona_id}/{uuid.uuid4()}.{ext}"

    # Ensure bucket exists (idempotent)
    try:
        db.storage.create_bucket(AVATAR_BUCKET, options={"public": True})
    except Exception:
        pass  # bucket already exists

    db.storage.from_(AVATAR_BUCKET).upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": content_type},
    )

    public_url = db.storage.from_(AVATAR_BUCKET).get_public_url(path)
    await update_persona_avatar(persona_id, user_id, public_url)
    return public_url


async def create_persona(user_id: str, data: PersonaCreate) -> Persona:
    db = get_db()
    result = (
        db.table("personas")
        .insert(
            {
                "user_id": user_id,
                "name": data.name,
                "stories": data.stories,
                "personality_traits": data.personality_traits,
                "speaking_style": data.speaking_style,
            }
        )
        .execute()
    )
    if not result.data:
        raise RuntimeError("Failed to create persona")
    return Persona(**result.data[0])


async def get_persona(persona_id: str, user_id: str) -> Persona | None:
    db = get_db()
    result = (
        db.table("personas")
        .select(
            "id, user_id, name, stories, personality_traits, speaking_style, voice_id, did_avatar_url, idle_video_url, simli_face_id, entity_graph, style_exemplars, created_at"
        )
        .eq("id", persona_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        return None
    return Persona(**result.data)


async def list_personas(user_id: str) -> list[Persona]:
    db = get_db()
    result = (
        db.table("personas")
        .select(
            "id, user_id, name, stories, personality_traits, speaking_style, voice_id, did_avatar_url, idle_video_url, simli_face_id, entity_graph, style_exemplars, created_at"
        )
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [Persona(**row) for row in result.data]


async def update_persona_voice(persona_id: str, user_id: str, voice_id: str) -> None:
    db = get_db()
    db.table("personas").update({"voice_id": voice_id}).eq("id", persona_id).eq(
        "user_id", user_id
    ).execute()


async def update_persona_avatar(persona_id: str, user_id: str, avatar_url: str) -> None:
    db = get_db()
    db.table("personas").update({"did_avatar_url": avatar_url}).eq("id", persona_id).eq(
        "user_id", user_id
    ).execute()


async def update_idle_video_url(persona_id: str, user_id: str, url: str) -> None:
    db = get_db()
    db.table("personas").update({"idle_video_url": url}).eq("id", persona_id).eq(
        "user_id", user_id
    ).execute()


async def update_persona_simli_face_id(persona_id: str, user_id: str, face_id: str) -> None:
    db = get_db()
    db.table("personas").update({"simli_face_id": face_id}).eq("id", persona_id).eq(
        "user_id", user_id
    ).execute()


async def delete_persona(persona_id: str, user_id: str) -> None:
    db = get_db()
    db.table("personas").delete().eq("id", persona_id).eq("user_id", user_id).execute()


async def update_entity_graph(persona_id: str, entity_graph: list[dict]) -> None:
    db = get_db()
    db.table("personas").update({"entity_graph": entity_graph}).eq("id", persona_id).execute()


async def update_style_exemplars(persona_id: str, style_exemplars: list[str]) -> None:
    db = get_db()
    db.table("personas").update({"style_exemplars": style_exemplars}).eq("id", persona_id).execute()
