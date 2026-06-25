"""Stage 0: normalize raw source material and stamp provenance.

Text      → strip + return as-is.
Audio/Video → Groq Whisper transcription (returns transcript + duration).
Document/Photo/Letter → pytesseract (printed) with Groq vision fallback (handwritten/hard).
PDF → pypdf text extraction; if empty → pdf2image first page → Groq vision.
"""
import base64
import io
import logging

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

_GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
_MAX_GROQ_BYTES = 25 * 1024 * 1024

_AUDIO_VIDEO_MODALITIES = {"audio", "video"}
_DOCUMENT_MODALITIES = {"document", "photo", "letter"}

_OCR_MIN_CHARS = 50  # below this, pytesseract result is considered insufficient


def _is_429(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


async def _transcribe_media(
    file_bytes: bytes, filename: str, content_type: str
) -> tuple[str, float]:
    """Send audio/video to Groq Whisper. Returns (transcript, duration_seconds)."""
    if settings.mock_mode:
        return "This is a mock transcription of the uploaded media.", 0.0

    if len(file_bytes) > _MAX_GROQ_BYTES:
        raise ValueError(
            f"File too large for transcription: {len(file_bytes):,} bytes "
            f"(Groq limit {_MAX_GROQ_BYTES:,})"
        )

    @retry(
        retry=retry_if_exception(_is_429),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(4),
    )
    async def _call() -> dict:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                _GROQ_WHISPER_URL,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                files={"file": (filename, file_bytes, content_type)},
                data={"model": "whisper-large-v3-turbo", "response_format": "verbose_json"},
            )
            response.raise_for_status()
            return response.json()

    data = await _call()
    transcript = data.get("text", "").strip()
    duration = float(data.get("duration", 0.0))
    logger.info("[Stage0] Whisper transcript len=%d duration=%.1fs", len(transcript), duration)
    return transcript, duration


def _pytesseract_ocr(file_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(file_bytes))
        return pytesseract.image_to_string(img).strip()
    except Exception as exc:
        logger.warning("[Stage0] pytesseract failed: %s", exc)
        return ""


def _pdf_text(file_bytes: bytes) -> str:
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception as exc:
        logger.warning("[Stage0] pypdf text extraction failed: %s", exc)
        return ""


def _pdf_first_page_png(file_bytes: bytes) -> bytes | None:
    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(file_bytes, first_page=1, last_page=1, dpi=200)
        if not images:
            return None
        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        logger.warning("[Stage0] pdf2image failed: %s", exc)
        return None


async def _groq_vision_ocr(file_bytes: bytes, content_type: str) -> str:
    """Call Groq vision model to extract text from an image."""
    b64 = base64.b64encode(file_bytes).decode()
    payload = {
        "model": _GROQ_VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{content_type};base64,{b64}"},
                },
                {
                    "type": "text",
                    "text": (
                        "Extract all text from this document image verbatim. "
                        "Return only the extracted text, no commentary."
                    ),
                },
            ],
        }],
        "max_tokens": 2048,
    }

    @retry(
        retry=retry_if_exception(_is_429),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(4),
    )
    async def _call() -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    text = await _call()
    logger.info("[Stage0] Groq vision OCR extracted %d chars", len(text))
    return text


async def _ocr_document(file_bytes: bytes, content_type: str) -> str:
    if settings.mock_mode:
        return "This is mock OCR text extracted from the document image."

    if "pdf" in content_type:
        text = _pdf_text(file_bytes)
        if len(text) >= _OCR_MIN_CHARS:
            logger.info("[Stage0] PDF text extraction: %d chars", len(text))
            return text
        png_bytes = _pdf_first_page_png(file_bytes)
        if png_bytes:
            return await _groq_vision_ocr(png_bytes, "image/png")
        logger.warning("[Stage0] PDF: no text extracted and pdf2image unavailable")
        return ""

    # Image file: pytesseract first, fall back to Groq vision if sparse
    text = _pytesseract_ocr(file_bytes)
    if len(text) >= _OCR_MIN_CHARS:
        logger.info("[Stage0] pytesseract OCR: %d chars", len(text))
        return text

    logger.info("[Stage0] pytesseract sparse (%d chars), trying Groq vision", len(text))
    return await _groq_vision_ocr(file_bytes, content_type)


async def normalize_source(
    modality: str,
    text_content: str,
    file_bytes: bytes | None,
    filename: str,
    content_type: str,
) -> tuple[str, tuple[float, float]]:
    """Dispatch to the right normalizer for the given modality.

    Returns (raw_text, timestamp_range).
    timestamp_range is (0.0, duration) for media, (0.0, 0.0) otherwise.
    """
    m = modality.lower()

    if m == "text":
        return text_content.strip(), (0.0, 0.0)

    if m == "video_audio":
        # Typed answer stored with video_audio modality (Guided Q&A flow).
        # Prefer text_content when present (typed path); fall back to media transcription
        # when file_bytes are provided; otherwise return empty cleanly.
        if text_content and text_content.strip():
            return text_content.strip(), (0.0, 0.0)
        if file_bytes:
            transcript, duration = await _transcribe_media(file_bytes, filename, content_type)
            return transcript, (0.0, duration)
        return "", (0.0, 0.0)

    if m in _AUDIO_VIDEO_MODALITIES:
        if not file_bytes:
            raise ValueError(f"File bytes required for modality '{modality}'")
        transcript, duration = await _transcribe_media(file_bytes, filename, content_type)
        return transcript, (0.0, duration)

    if m in _DOCUMENT_MODALITIES:
        if not file_bytes:
            raise ValueError(f"File bytes required for modality '{modality}'")
        text = await _ocr_document(file_bytes, content_type)
        return text, (0.0, 0.0)

    raise ValueError(f"Unknown modality: '{modality}'")


async def transcribe_media(
    file_bytes: bytes, filename: str, content_type: str
) -> tuple[str, float]:
    """Public interface: Groq Whisper STT for a full audio/video file.

    Used by the creation flow for a/v capture; distinct from stt.transcribe_audio
    which handles real-time PCM chunks from the WebSocket path.
    Returns (transcript, duration_seconds).
    """
    return await _transcribe_media(file_bytes, filename, content_type)
