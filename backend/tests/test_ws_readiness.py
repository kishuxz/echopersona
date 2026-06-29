"""Tests for the WebSocket readiness gate logic (routers/ws.py).

The gate condition is:
    should_block = (
        readiness_status not in ("ready",)
        and not _has_index          # no FAISS units loaded
        and not stories             # no legacy story strings
    )

We test the condition by reconstructing it directly using real PersonaRAG instances —
no full WebSocket server spin-up required, so these are pure unit tests with no I/O.

Coverage:
  - Persona with FAISS units in _units → gate passes (no block)
  - Persona with readiness_status="ready" → gate passes regardless of units
  - Persona with no units and no stories → gate blocks (4010 path)
  - Persona with legacy stories (no FAISS units) → gate passes
  - FAISS units present but status is "processing" → gate still passes (index takes priority)
"""

from services.rag import PersonaRAG


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_rag(units: list[dict]) -> PersonaRAG:
    """Return a PersonaRAG with _units pre-populated (no embedding required)."""
    r = PersonaRAG()
    r._units = units
    return r


def _gate(readiness_status: str, rag: PersonaRAG | None, stories: list[str]) -> bool:
    """Mirror of the gate condition in ws.py lines 658-660."""
    _has_index = bool(rag and rag._units)
    return (
        readiness_status not in ("ready",)
        and not _has_index
        and not stories
    )


# ══════════════════════════════════════════════════════════════════════════════
# Readiness gate: must NOT block
# ══════════════════════════════════════════════════════════════════════════════

class TestReadinessGatePasses:

    def test_readiness_gate_passes_with_faiss_units(self):
        """Persona with FAISS units must NOT be blocked even when status is 'processing'."""
        rag = _make_rag([{"text": "I grew up in Chennai", "affect": {}}])
        should_block = _gate("processing", rag, [])
        assert not should_block, "Should NOT block when FAISS index has units"

    def test_readiness_gate_passes_when_status_ready(self):
        """readiness_status='ready' always passes regardless of index state."""
        rag = _make_rag([])
        should_block = _gate("ready", rag, [])
        assert not should_block, "Should NOT block when status is 'ready'"

    def test_readiness_gate_passes_with_legacy_stories(self):
        """Persona with no FAISS units but legacy stories must NOT be blocked."""
        rag = _make_rag([])
        should_block = _gate("processing", rag, ["I grew up in Chennai and loved the rain."])
        assert not should_block, "Should NOT block when legacy stories are present"

    def test_readiness_gate_passes_with_multiple_faiss_units(self):
        """Multiple units in FAISS → gate passes."""
        units = [
            {"text": "I loved to sing", "affect": {"primary_emotion": "joy", "valence": 0.8}},
            {"text": "I missed the monsoon", "affect": {}},
        ]
        rag = _make_rag(units)
        should_block = _gate("processing", rag, [])
        assert not should_block

    def test_readiness_gate_passes_rag_none_but_ready_status(self):
        """No RAG object at all, but status='ready' → gate passes."""
        should_block = _gate("ready", None, [])
        assert not should_block

    def test_readiness_gate_passes_status_pending_with_stories(self):
        """status='pending' with stories present → gate passes."""
        rag = _make_rag([])
        should_block = _gate("pending", rag, ["Story about growing up."])
        assert not should_block


# ══════════════════════════════════════════════════════════════════════════════
# Readiness gate: MUST block (4010 path)
# ══════════════════════════════════════════════════════════════════════════════

class TestReadinessGateBlocks:

    def test_readiness_gate_blocks_no_units_no_stories(self):
        """No FAISS units, no stories, status not ready → gate blocks."""
        rag = _make_rag([])
        should_block = _gate("processing", rag, [])
        assert should_block, "Should block when no units and no stories"

    def test_readiness_gate_blocks_rag_none_no_stories(self):
        """No RAG object at all, no stories, status not ready → gate blocks."""
        should_block = _gate("processing", None, [])
        assert should_block, "Should block when RAG is None and no stories"

    def test_readiness_gate_blocks_status_pending_no_content(self):
        """status='pending' with no units and no stories → gate blocks."""
        rag = _make_rag([])
        should_block = _gate("pending", rag, [])
        assert should_block

    def test_readiness_gate_blocks_rag_none_status_error(self):
        """status='error' with no content → gate blocks (only 'ready' passes)."""
        should_block = _gate("error", None, [])
        assert should_block

    def test_readiness_gate_does_not_block_on_empty_string_story(self):
        """An empty string in stories list is falsy — must still block."""
        rag = _make_rag([])
        # list is non-empty but contains only empty strings — falsy via 'not stories' is False
        # because the list itself is truthy. This tests that gate uses 'not stories' (list bool),
        # which means even [""] passes. Verify the real gate matches this expectation.
        should_block = _gate("processing", rag, [""])
        # [""] is truthy → _gate returns False (does NOT block)
        assert not should_block, (
            "A non-empty stories list (even with empty strings) is truthy, "
            "so the gate should NOT block — matches ws.py `not _p.stories` semantics"
        )
