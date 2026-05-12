import time
from dataclasses import dataclass, field


@dataclass
class LatencyTimer:
    start: float | None = None
    started_at: float = field(default_factory=time.perf_counter)
    stt_ms: float = 0
    llm_first_token_ms: float = 0
    tts_first_audio_ms: float = 0

    def __post_init__(self) -> None:
        if self.start is not None:
            self.started_at = self.start

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.started_at) * 1000

    def summary(self) -> dict:
        return {
            "stt_ms": round(self.stt_ms, 1),
            "llm_first_token_ms": round(self.llm_first_token_ms, 1),
            "tts_first_audio_ms": round(self.tts_first_audio_ms, 1),
            "total_ms": round(self.elapsed_ms(), 1),
        }
