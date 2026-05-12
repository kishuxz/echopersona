from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: str
    content: str


class LatencySnapshot(BaseModel):
    stt_ms: float = 0
    llm_first_token_ms: float = 0
    tts_first_audio_ms: float = 0
    total_ms: float = 0


class SessionState(BaseModel):
    session_id: str
    persona_id: str | None = None
    history: list[ConversationTurn] = Field(default_factory=list)
