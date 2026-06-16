import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from middleware.auth import get_current_user
from services.ingestion.source_store import create_source_record, upload_source_file
from services.persona_store import get_persona

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])

_FILE_MODALITIES = {"audio", "video", "document", "photo", "letter"}


@router.post("/{persona_id}")
async def ingest_source(
    persona_id: str,
    request: Request,
    modality: str = Form(...),
    question_category: str = Form(""),
    question_text: str = Form(""),
    group_name: str = Form(""),
    text_content: str = Form(""),
    file: UploadFile | None = File(None),
    user_id: str = Depends(get_current_user),
) -> dict:
    """Accept raw source material, store it, and enqueue the ingestion pipeline."""
    persona = await get_persona(persona_id, user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    if modality.lower() in _FILE_MODALITIES and file is None:
        raise HTTPException(
            status_code=400, detail=f"File required for modality '{modality}'"
        )

    file_id = ""
    if file is not None:
        file_bytes = await file.read()
        file_id = await upload_source_file(
            user_id=user_id,
            file_bytes=file_bytes,
            content_type=file.content_type or "application/octet-stream",
            filename=file.filename or "upload",
        )

    source_id = await create_source_record(
        user_id=user_id,
        persona_id=persona_id,
        modality=modality,
        question_category=question_category,
        question_text=question_text,
        group_name=group_name,
        file_id=file_id,
        text_content=text_content,
    )

    arq_pool = request.app.state.arq_pool
    job = await arq_pool.enqueue_job("ingest_memory_unit", source_id, user_id)
    job_id = job.job_id if job else None

    logger.info(
        "Enqueued ingest_memory_unit source_id=%s job_id=%s", source_id, job_id
    )
    return {"source_id": source_id, "status": "queued", "job_id": job_id}
