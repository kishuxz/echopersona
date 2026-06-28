"""Shared test fixtures."""
import pytest
from unittest.mock import patch
import services.entitlements as _ent_mod


@pytest.fixture(autouse=True)
def disable_voice_always_on():
    """Prevent VOICE_ALWAYS_ON=true in dev .env from bypassing entitlement assertions.
    Uses patch.object on the real settings instance so TestVoiceAlwaysOn can override it."""
    with patch.object(_ent_mod.settings, "voice_always_on", False):
        yield
