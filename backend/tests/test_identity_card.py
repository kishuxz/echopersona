"""Tests for Stage 4B identity card extraction, coercion, and Groq integration.

Coverage:
  1. empty_units_returns_mock: extract_identity_card([]) returns all-6-key dict with safe defaults
  2. mock_mode_returns_safe_defaults: mock_mode=True skips httpx and returns _mock_identity_card()
  3. coerce_values_not_list: non-list values field → coerced to []
  4. coerce_values_stripped_and_capped: list items are stripped and capped at 40 chars
  5. coerce_values_list_capped_at_5: input 6 items → output has exactly 5
  6. coerce_string_non_string_to_empty: non-string string field → ""
  7. coerce_string_over_length_capped: string > 200 chars is truncated to 200
  8. all_6_keys_always_present: _coerce_identity_card({}) always emits all 6 keys
  9. happy_path_mock_groq: valid Groq JSON → role_identity and values populated
  10. groq_failure_returns_mock: Groq HTTP 500 → returns _mock_identity_card(), no raise

All Groq/httpx calls are mocked. No live API calls.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ingestion.stage4b import (
    _coerce_identity_card,
    _mock_identity_card,
    extract_identity_card,
)

# ── shared fixtures ────────────────────────────────────────────────────────────

_SAMPLE_UNITS = [
    {
        "content_first_person": "I believe family comes first above everything else.",
        "memory_category": "values",
    },
    {
        "content_first_person": "I have always seen the world as a place where hard work pays off.",
        "memory_category": "semantic",
    },
]

_EXPECTED_KEYS = {
    "values",
    "worldview",
    "role_identity",
    "emotional_wiring",
    "communication_style",
    "life_philosophy",
}


# ── 1. empty_units_returns_mock ───────────────────────────────────────────────

def test_empty_units_returns_mock():
    """extract_identity_card([]) must return the 6-key safe-default dict without hitting Groq."""
    result = asyncio.run(extract_identity_card([]))

    assert set(result.keys()) == _EXPECTED_KEYS
    assert result["values"] == []
    assert result["worldview"] == ""
    assert result["role_identity"] == ""
    assert result["emotional_wiring"] == ""
    assert result["communication_style"] == ""
    assert result["life_philosophy"] == ""


# ── 2. mock_mode_returns_safe_defaults ────────────────────────────────────────

def test_mock_mode_returns_safe_defaults():
    """When settings.mock_mode=True, no httpx call is made and safe defaults are returned."""
    with patch("services.ingestion.stage4b.settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_settings.mock_mode = True

        result = asyncio.run(extract_identity_card(_SAMPLE_UNITS))

        mock_client_cls.assert_not_called()

    assert set(result.keys()) == _EXPECTED_KEYS
    assert result["values"] == []
    assert result["role_identity"] == ""


# ── 3. coerce_values_not_list ─────────────────────────────────────────────────

def test_coerce_values_not_list():
    """A non-list values field must be coerced to an empty list, not crash."""
    result = _coerce_identity_card({"values": "family"})
    assert result["values"] == []


# ── 4. coerce_values_stripped_and_capped ──────────────────────────────────────

def test_coerce_values_stripped_and_capped():
    """List items must be stripped of whitespace and each capped at 40 characters."""
    long_value = "  " + ("x" * 50) + "  "          # 54 chars with padding
    result = _coerce_identity_card({"values": [long_value, "  family first  "]})

    assert result["values"][0] == "x" * 40           # stripped + capped
    assert result["values"][1] == "family first"     # stripped, under limit


# ── 5. coerce_values_list_capped_at_5 ────────────────────────────────────────

def test_coerce_values_list_capped_at_5():
    """A list of 6 values must be trimmed to at most 5 entries."""
    six_values = [f"value{i}" for i in range(6)]
    result = _coerce_identity_card({"values": six_values})
    assert len(result["values"]) == 5


# ── 6. coerce_string_non_string_to_empty ──────────────────────────────────────

def test_coerce_string_non_string_to_empty():
    """A non-string worldview (e.g. int) must be coerced to empty string."""
    result = _coerce_identity_card({"worldview": 42})
    assert result["worldview"] == ""


# ── 7. coerce_string_over_length_capped ──────────────────────────────────────

def test_coerce_string_over_length_capped():
    """A string field exceeding 200 characters must be truncated to exactly 200."""
    long_string = "a" * 250
    result = _coerce_identity_card({"life_philosophy": long_string})
    assert len(result["life_philosophy"]) == 200
    assert result["life_philosophy"] == "a" * 200


# ── 8. all_6_keys_always_present ─────────────────────────────────────────────

def test_all_6_keys_always_present():
    """_coerce_identity_card({}) must emit exactly the 6 canonical keys, no more, no less."""
    result = _coerce_identity_card({})
    assert set(result.keys()) == _EXPECTED_KEYS


# ── 9. happy_path_mock_groq ───────────────────────────────────────────────────

def test_happy_path_mock_groq():
    """A well-formed Groq response must be parsed into a populated identity card."""
    groq_payload = {
        "values": ["family first", "honest work", "curiosity"],
        "worldview": "The world rewards those who show up with integrity every day.",
        "role_identity": "A builder and keeper of family stories across generations.",
        "emotional_wiring": "Processes feelings quietly then speaks from a place of calm.",
        "communication_style": "Listens deeply before offering a measured, direct opinion.",
        "life_philosophy": "Leave every person you meet a little better than you found them.",
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(groq_payload)}}]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("services.ingestion.stage4b.settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_settings.mock_mode = False
        mock_settings.groq_api_key = "test-key"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = asyncio.run(extract_identity_card(_SAMPLE_UNITS))

    assert result["role_identity"] != ""
    assert isinstance(result["values"], list)
    assert len(result["values"]) > 0
    assert set(result.keys()) == _EXPECTED_KEYS


# ── 10. groq_failure_returns_mock ─────────────────────────────────────────────

def test_groq_failure_returns_mock():
    """An HTTP 500 from Groq must not raise; the function returns _mock_identity_card() instead."""
    with patch("services.ingestion.stage4b.settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_settings.mock_mode = False
        mock_settings.groq_api_key = "test-key"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        # Simulate an HTTP 500 by raising HTTPStatusError
        error_response = MagicMock()
        error_response.status_code = 500
        mock_client.post = AsyncMock(
            side_effect=Exception("500 Internal Server Error")
        )
        mock_client_cls.return_value = mock_client

        # Must not raise
        result = asyncio.run(extract_identity_card(_SAMPLE_UNITS))

    assert set(result.keys()) == _EXPECTED_KEYS
    assert result["values"] == []
    assert result["worldview"] == ""
    assert result["role_identity"] == ""
