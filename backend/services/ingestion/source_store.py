"""Supabase Storage + DB layer for raw ingestion source items."""
import logging
import uuid

from services.db import get_db

logger = logging.getLogger(__name__)

SOURCE_BUCKET = "ingestion-sources"


def _ensure_bucket() -> None:
    db = get_db()
    try:
        db.storage.create_bucket(SOURCE_BUCKET, options={"public": False})
    except Exception:
        pass  # already exists


async def upload_source_file(
    user_id: str, file_bytes: bytes, content_type: str, filename: str
) -> str:
    """Upload raw source file to Supabase Storage. Returns the storage path (file_id)."""
    _ensure_bucket()
    db = get_db()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    path = f"{user_id}/{uuid.uuid4()}.{ext}"
    db.storage.from_(SOURCE_BUCKET).upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": content_type},
    )
    return path


async def download_source_file(file_id: str) -> bytes:
    """Download raw source file from Supabase Storage."""
    db = get_db()
    return db.storage.from_(SOURCE_BUCKET).download(file_id)


async def create_source_record(
    user_id: str,
    persona_id: str,
    modality: str,
    question_category: str,
    question_text: str,
    group_name: str,
    file_id: str,
    text_content: str,
    source_question_id: str = "",
    source_type: str = "answer",
    media_ref: str = "",
    captured_at: str = "",
) -> str:
    """Insert a row in memory_sources. Returns the new source_id (UUID string)."""
    db = get_db()
    result = (
        db.table("memory_sources")
        .insert({
            "user_id": user_id,
            "persona_id": persona_id,
            "modality": modality,
            "question_category": question_category,
            "question_text": question_text,
            "source_question_id": source_question_id,
            "source_type": source_type,
            "group_name": group_name,
            "file_id": file_id,
            "media_ref": media_ref,
            "text_content": text_content,
            "captured_at": captured_at or None,
            "status": "pending",
        })
        .execute()
    )
    if not result.data:
        raise RuntimeError("Failed to create memory_sources record")
    return result.data[0]["id"]


async def get_source_record(source_id: str) -> dict | None:
    db = get_db()
    result = (
        db.table("memory_sources")
        .select("*")
        .eq("id", source_id)
        .maybe_single()
        .execute()
    )
    return result.data


async def update_source_status(
    source_id: str,
    status: str,
    raw_text: str = "",
    timestamp_range: tuple[float, float] = (0.0, 0.0),
) -> None:
    db = get_db()
    updates: dict = {"status": status}
    if raw_text:
        updates["raw_text"] = raw_text
        updates["timestamp_range"] = list(timestamp_range)
    db.table("memory_sources").update(updates).eq("id", source_id).execute()


async def write_memory_unit(
    user_id: str,
    persona_id: str,
    source_id: str,
    source_meta: dict,
    content_first_person: str,
    memory_category: str,
    stance: str,
    affect: dict,
    themes: list[str],
    entities: dict,
    version: int = 1,
    supersedes: str | None = None,
) -> str:
    """Insert one row into memory_units. Returns the new unit_id.

    version/supersedes are §2.3 [add-004] fields: version defaults to 1;
    supersedes is set only for corrections (§6/§7.1, step 5).
    memory_category is the semantic type from Stage 2 — migration 007.
    Requires migrations 004 and 007 to be applied before use against a live DB.
    """
    db = get_db()
    result = (
        db.table("memory_units")
        .insert({
            "user_id": user_id,
            "persona_id": persona_id,
            "source_id": source_id,
            "source": source_meta,
            "content_first_person": content_first_person,
            "memory_category": memory_category,
            "stance": stance,
            "affect": affect,
            "themes": themes,
            "entities": entities,
            "version": version,
            "supersedes": supersedes,
            "verified": False,
            "embedding": [],
            "fidelity_flags": [],
            "fidelity_score": 1.0,
        })
        .execute()
    )
    if not result.data:
        raise RuntimeError("Failed to insert memory_unit")
    return result.data[0]["unit_id"]


async def update_unit_fidelity(
    unit_id: str,
    fidelity_flags: list[dict],
    fidelity_score: float,
) -> None:
    """Write fidelity check results back onto the unit row."""
    db = get_db()
    db.table("memory_units").update({
        "fidelity_flags": fidelity_flags,
        "fidelity_score": fidelity_score,
    }).eq("unit_id", unit_id).execute()


async def get_memory_units_for_source(source_id: str) -> list[dict]:
    db = get_db()
    result = (
        db.table("memory_units")
        .select("*")
        .eq("source_id", source_id)
        .execute()
    )
    return result.data or []


async def get_memory_unit(unit_id: str) -> dict | None:
    """Fetch a single memory_unit row by its unit_id."""
    db = get_db()
    result = (
        db.table("memory_units")
        .select("*")
        .eq("unit_id", unit_id)
        .maybe_single()
        .execute()
    )
    return result.data


async def get_memory_units_for_persona(
    persona_id: str,
    verified_only: bool = False,
    exclude_superseded: bool = False,
) -> list[dict]:
    """Load all memory_units for a persona, sorted by creation time.

    exclude_superseded=True drops units whose unit_id appears in the
    supersedes field of any other unit — i.e. units that have been replaced
    by a correction (§6/§7.1). Old versions stay in the DB for audit but
    must not appear in live retrieval.
    """
    db = get_db()

    superseded_ids: set[str] = set()
    if exclude_superseded:
        sup_result = (
            db.table("memory_units")
            .select("supersedes")
            .eq("persona_id", persona_id)
            .not_.is_("supersedes", "null")
            .execute()
        )
        superseded_ids = {str(row["supersedes"]) for row in (sup_result.data or [])}

    q = (
        db.table("memory_units")
        .select("*")
        .eq("persona_id", persona_id)
        .order("created_at", desc=False)
    )
    if verified_only:
        q = q.eq("verified", True)
    if superseded_ids:
        q = q.not_.in_("unit_id", list(superseded_ids))
    result = q.execute()
    return result.data or []
