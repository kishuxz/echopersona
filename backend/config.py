from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).parent / ".env", env_file_encoding="utf-8", extra="ignore")

    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field(default="", alias="ELEVENLABS_VOICE_ID")

    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    max_concurrent_sessions: int = Field(default=100, alias="MAX_CONCURRENT_SESSIONS")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")

    did_api_key: str = Field(default="", alias="DID_API_KEY")
    did_default_source_url: str = Field(default="", alias="DID_DEFAULT_SOURCE_URL")

    simli_api_key: str = Field(default="", alias="SIMLI_API_KEY")

    tavus_api_key: str = Field(default="", alias="TAVUS_API_KEY")

    vllm_base_url: str = Field(default="", alias="VLLM_BASE_URL")
    use_vllm: bool = Field(default=False, alias="USE_VLLM")

    tts_provider: str = Field(default="elevenlabs", alias="TTS_PROVIDER")  # "elevenlabs" | "cartesia"
    cartesia_api_key: str = Field(default="", alias="CARTESIA_API_KEY")
    cartesia_voice_id: str = Field(default="", alias="CARTESIA_VOICE_ID")

    stt_provider: str = Field(default="groq", alias="STT_PROVIDER")  # "groq" | "deepgram"
    deepgram_api_key: str = Field(default="", alias="DEEPGRAM_API_KEY")

    public_base_url: str = Field(default="https://kishoreai.online", alias="PUBLIC_BASE_URL")

    stripe_secret_key: str = Field(default="", alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_creator_monthly: str = Field(default="", alias="STRIPE_PRICE_CREATOR_MONTHLY")
    stripe_price_legacy_monthly: str = Field(default="", alias="STRIPE_PRICE_LEGACY_MONTHLY")
    stripe_price_preservation_onetime: str = Field(default="", alias="STRIPE_PRICE_PRESERVATION_ONETIME")
    stripe_price_posthumous_monthly: str = Field(default="", alias="STRIPE_PRICE_POSTHUMOUS_MONTHLY")
    enforce_answer_quotas: bool = Field(default=False, alias="ENFORCE_ANSWER_QUOTAS")
    frontend_billing_success_url: str = Field(
        default="http://localhost:5173/billing/success",
        alias="FRONTEND_BILLING_SUCCESS_URL",
    )
    frontend_billing_cancel_url: str = Field(
        default="http://localhost:5173/billing/cancel",
        alias="FRONTEND_BILLING_CANCEL_URL",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    resend_from_address: str = Field(default="noreply@kishoreai.online", alias="RESEND_FROM_ADDRESS")

    voice_always_on: bool = Field(default=False, alias="VOICE_ALWAYS_ON")
    force_mock_mode: bool = Field(default=False, alias="MOCK_MODE")

    @property
    def mock_mode(self) -> bool:
        return self.force_mock_mode or not (self.groq_api_key and self.elevenlabs_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
