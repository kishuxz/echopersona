"""Persona RAG: embed memory_units, FAISS retrieval, system-prompt builder.

Index priority for a persona:
  1. memory_units from Supabase (Stage 1-2 pipeline output, richer content)
  2. persona.stories (legacy fallback for personas that pre-date the pipeline)

retrieve() returns list[dict] — always has "text" key, may have:
  stance, themes, entities  (when built from memory_units)
"""
import logging
import re

import numpy as np

from config import settings
from models.consent import ListenerContext
from models.persona import Persona, PersonaCreate

logger = logging.getLogger(__name__)

_EMBED_MODEL = "paraphrase-MiniLM-L3-v2"
# §9.7 confidence floor — units scoring below this are treated as no-match
_SCORE_THRESHOLD = 0.25
# Boost applied to units whose resolved_entity_ids includes the listener's entity
_ENTITY_BOOST = 0.15


class PersonaRAG:
    def __init__(self) -> None:
        self.model = None
        self.index = None
        self._units: list[dict] = []  # parallel to FAISS rows — each dict has at least "text"

    # ── model loading ───────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(_EMBED_MODEL)

    # ── index building ──────────────────────────────────────────────────────

    def _build_faiss(self, texts: list[str]) -> None:
        if not texts or settings.mock_mode:
            self.index = None
            return
        self._load()
        embeddings = self.model.encode(texts)
        embeddings = np.asarray(embeddings, dtype=np.float32)
        try:
            import faiss
            faiss.normalize_L2(embeddings)
            idx = faiss.IndexFlatIP(embeddings.shape[1])
            idx.add(embeddings)
            self.index = idx
        except Exception:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            self.index = embeddings / np.maximum(norms, 1e-12)

    def build_index_from_units(self, units: list[dict]) -> None:
        """Build index from Supabase memory_unit rows.

        Each unit must have 'content_first_person'. Optional: stance, themes, entities.
        """
        self._units = []
        texts: list[str] = []
        for u in units:
            text = (u.get("content_first_person") or "").strip()
            if not text:
                continue
            self._units.append({
                "text": text,
                "stance": u.get("stance", ""),
                "themes": u.get("themes") or [],
                "entities": u.get("entities") or {},
                "affect": u.get("affect") or {},
                "resolved_entity_ids": list(u.get("resolved_entity_ids") or []),
            })
            texts.append(text)
        self._build_faiss(texts)
        logger.info("[RAG] built index from %d memory units", len(texts))

    def build_index(self, stories: list[str]) -> None:
        """Legacy: build index from plain story strings (150-word chunks)."""
        chunks = self._chunk_stories(stories)
        self._units = [{"text": c} for c in chunks]
        self._build_faiss(chunks)
        logger.info("[RAG] built legacy index from %d chunks", len(chunks))

    @staticmethod
    def _chunk_stories(stories: list[str]) -> list[str]:
        chunks: list[str] = []
        for story in stories:
            words = story.split()
            if not words:
                continue
            for start in range(0, len(words), 150):
                chunk = " ".join(words[start:start + 150])
                if chunk:
                    chunks.append(chunk)
        return chunks

    # ── retrieval ───────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        listener_entity: str | None = None,
    ) -> list[dict]:
        """Return top-k matching units as dicts with at least a 'text' key.

        listener_entity: canonical entity name (from persona_relationships). When
        provided, units whose resolved_entity_ids includes this name receive a
        score boost so listener-relevant memories surface higher (§9.3).

        Units scoring below _SCORE_THRESHOLD are dropped; if all drop the
        no-memory fallback in build_system_prompt takes over (§9.7).
        """
        if not self._units:
            return []

        if self.index is None or settings.mock_mode:
            # Keyword fallback — no threshold or boost in mock mode
            query_terms = set(query.lower().split())
            scored = [
                (len(query_terms & set(u["text"].lower().split())), i)
                for i, u in enumerate(self._units)
            ]
            scored.sort(reverse=True)
            indices = [i for _, i in scored[:top_k] if scored[0][0] > 0]
            return [self._units[i] for i in indices] or self._units[:top_k]

        self._load()
        q_emb = np.asarray(self.model.encode([query]), dtype=np.float32)

        try:
            import faiss
            faiss.normalize_L2(q_emb)
            # Fetch extra candidates so threshold filtering still yields top_k
            n_candidates = min(len(self._units), top_k * 3)
            scores_raw, idxs = self.index.search(q_emb, n_candidates)
            scores = scores_raw[0]
            indices_raw = idxs[0]
        except Exception:
            norms = np.linalg.norm(q_emb, axis=1, keepdims=True)
            q_emb_norm = q_emb / np.maximum(norms, 1e-12)
            scores = np.asarray(self.index) @ q_emb_norm[0]
            indices_raw = np.argsort(scores)[::-1][:top_k * 3]
            scores = scores[indices_raw]

        # Apply entity boost, then threshold filter
        entity_lower = listener_entity.lower() if listener_entity else ""
        boosted: list[tuple[float, int]] = []
        for score, idx in zip(scores, indices_raw):
            if not (0 <= idx < len(self._units)):
                continue
            s = float(score)
            if entity_lower:
                unit_entities = [e.lower() for e in self._units[idx].get("resolved_entity_ids") or []]
                if entity_lower in unit_entities:
                    s += _ENTITY_BOOST
            boosted.append((s, idx))

        boosted.sort(key=lambda x: x[0], reverse=True)
        result = [
            self._units[idx]
            for s, idx in boosted[:top_k]
            if s >= _SCORE_THRESHOLD
        ]
        return result


# ── process-level cache ─────────────────────────────────────────────────────

PERSONAS: dict[str, Persona] = {}
RAG_INDICES: dict[str, PersonaRAG] = {}


# ── system prompt ───────────────────────────────────────────────────────────

def _truncate(text: str, max_words: int = 80) -> str:
    words = text.split()
    return " ".join(words[:max_words])


def _valence_label(valence: float | None) -> str:
    if valence is None:
        return "neutral"
    if valence > 0.3:
        return "warm"
    if valence < -0.3:
        return "somber"
    return "neutral"


def build_system_prompt(
    persona: Persona | None,
    retrieved_context: list[dict] | list[str],
    listener_ctx: ListenerContext | None = None,
) -> str:
    if persona is None:
        return (
            "You are a helpful AI having a voice conversation. "
            "Answer naturally in 1-2 short sentences. Never use lists or formatting."
        )

    # Normalise: accept both list[dict] (units) and list[str] (legacy)
    units: list[dict] = []
    for item in retrieved_context:
        if isinstance(item, str):
            units.append({"text": item})
        elif isinstance(item, dict):
            units.append(item)

    # Memory block
    def _affect_tag(u: dict) -> str:
        affect = u.get("affect") or {}
        # Strip newlines and cap length to prevent prompt injection via ingestion LLM output
        emotion = re.sub(r"[\r\n]+", " ", (affect.get("primary_emotion") or "").strip())[:40]
        raw_valence = affect.get("valence")
        valence = float(raw_valence) if raw_valence is not None else None
        if emotion:
            return f"[{emotion}, {_valence_label(valence)}] {u['text']}"
        return u["text"]

    memory_lines = [_affect_tag(u) for u in units] if units else []
    if memory_lines:
        context_block = "\n".join(f"- {m}" for m in memory_lines)
        no_memory_fallback = ""
    else:
        context_block = "No memories available yet."
        no_memory_fallback = (
            "\n\nFALLBACK: If no relevant memory is available, say only: "
            "\"That's not something I can quite place right now. "
            "Tell me what you remember — sometimes hearing it from you brings it back to me.\" "
            "Do not add more. Do not fabricate. Do not use outside knowledge about this name."
        )

    # Identity block — WHO the persona IS (Layer 1)
    stances = [u["stance"] for u in units if u.get("stance")]
    dominant_stance = stances[0] if stances else ""

    ic = persona.identity_card if isinstance(getattr(persona, "identity_card", None), dict) else {}
    identity_parts: list[str] = []

    if ic:
        # Stage 4B identity card fields
        role_identity = (ic.get("role_identity") or "").strip()
        if role_identity:
            identity_parts.append(role_identity)
        values = [v for v in (ic.get("values") or []) if isinstance(v, str) and v.strip()]
        if values:
            identity_parts.append(f"Core values: {', '.join(values)}.")
        worldview = (ic.get("worldview") or "").strip()
        if worldview:
            identity_parts.append(worldview)
    else:
        # Legacy fallback for personas that pre-date Stage 4B
        if persona.personality_traits:
            identity_parts.append(f"Personality: {', '.join(persona.personality_traits)}.")
        if persona.speaking_style:
            identity_parts.append(f"Speaking style: {persona.speaking_style}.")

    if dominant_stance:
        identity_parts.append(f"Speak with a {dominant_stance} tone when discussing related memories.")

    identity_block = " ".join(identity_parts)

    # Entity context from Stage 3 entity graph
    entity_block = ""
    if persona.entity_graph:
        people = [
            e["canonical"]
            for e in persona.entity_graph
            if e.get("type") == "person" and e.get("canonical")
        ][:6]
        places = [
            e["canonical"]
            for e in persona.entity_graph
            if e.get("type") == "place" and e.get("canonical")
        ][:4]
        parts = []
        if people:
            parts.append(f"People: {', '.join(people)}")
        if places:
            parts.append(f"Places: {', '.join(places)}")
        if parts:
            entity_block = "\nKEY CONTEXT — " + " | ".join(parts) + "."

    # Voice card from Stage 4 — structured speech style (migration 008)
    voice_block = ""
    if persona.voice_card:
        vc = persona.voice_card
        vc_lines: list[str] = []
        formality = (vc.get("formality") or "").strip()
        if formality:
            vc_lines.append(f"- Speak with {formality} formality.")
        address_terms = [t for t in (vc.get("address_terms") or []) if t]
        if address_terms:
            vc_lines.append("- Address people as: " + ", ".join(f'"{t}"' for t in address_terms))
        catchphrases = [p for p in (vc.get("catchphrases") or []) if p]
        if catchphrases:
            vc_lines.append("- Use naturally: " + ", ".join(f'"{p}"' for p in catchphrases))
        humor_style = (vc.get("humor_style") or "").strip()
        if humor_style:
            vc_lines.append(f"- Humor style: {humor_style}")
        sentence_rhythm = (vc.get("sentence_rhythm") or "").strip()
        if sentence_rhythm:
            vc_lines.append(f"- Sentence rhythm: {sentence_rhythm}")
        emotional_tone = (vc.get("emotional_tone") or "").strip()
        if emotional_tone:
            vc_lines.append(f"- Emotional tone: {emotional_tone}")
        advice_style = (vc.get("advice_style") or "").strip()
        if advice_style:
            vc_lines.append(f"- Advice style: {advice_style}")
        verbal_tics = [t for t in (vc.get("verbal_tics") or []) if t]
        if verbal_tics:
            vc_lines.append("- Verbal tics: " + ", ".join(f'"{t}"' for t in verbal_tics))
        if vc_lines:
            voice_block = "\nVOICE & STYLE:\n" + "\n".join(vc_lines)

    # Phase 2 style fields — relationship-aware tone override for non-owner listeners
    effective_tone = persona.tone
    if (
        listener_ctx is not None
        and not listener_ctx.is_owner
        and listener_ctx.relationship
        and persona.relationship_tone.get(listener_ctx.relationship)
    ):
        effective_tone = persona.relationship_tone[listener_ctx.relationship]

    style_instructions: list[str] = []
    if effective_tone:
        style_instructions.append(f"Tone: {effective_tone}.")
    if persona.avoid_phrases:
        style_instructions.append(f"Prefer not to use: {', '.join(persona.avoid_phrases)}.")
    if persona.answer_length_pref:
        style_instructions.append(f"Keep responses {persona.answer_length_pref}.")

    style_block = ""
    if style_instructions:
        style_block += "\nSTYLE: " + " ".join(style_instructions)
    if persona.style_exemplars:
        ex = persona.style_exemplars[:3]
        style_block += "\nCHARACTERISTIC PHRASES:\n" + "\n".join(f'  "{e}"' for e in ex)

    # Listener context block — only for authenticated non-owner beneficiaries
    listener_block = ""
    if listener_ctx is not None and not listener_ctx.is_owner:
        lines = ["LISTENER CONTEXT:"]
        if listener_ctx.relationship:
            lines.append(f"You are speaking with the persona owner's {listener_ctx.relationship}.")
        if listener_ctx.address_term:
            lines.append(
                f'When naturally greeting this listener, you may address them as "{listener_ctx.address_term}".'
            )
        if listener_ctx.closeness_level is not None:
            lines.append(f"Closeness level: {listener_ctx.closeness_level}/5.")
        if listener_ctx.greeting_style:
            lines.append(f"Greeting style: {listener_ctx.greeting_style}.")
        if listener_ctx.scope:
            lines.append(f"Access scope: {listener_ctx.scope}.")
        lines.append("Do not infer listener identity beyond this authenticated context.")
        lines.append(
            "Do not assert shared memories, family events, or private facts "
            "unless they appear in YOUR MEMORIES above."
        )
        listener_block = "\n" + "\n".join(lines)

    prompt = (
        # Layer 1 — Identity (sentence cap removed from here)
        f"You are {persona.name}. Speak only in first person.\n"
        f"IMPORTANT: Use ONLY the memories below. Ignore all outside knowledge about this name.\n"
        f"{identity_block}\n"
        # Layer 2 — Memories (affect-tagged; tags are internal context — never repeat them in replies)
        f"\nYOUR MEMORIES (the bracketed tags are internal context cues — never mention them in your reply):\n{context_block}"
        f"{no_memory_fallback}"
        # Layer 3 — Listener context (moved from last to third)
        f"{listener_block}"
        # Layer 4 — Voice + style
        f"{voice_block}"
        f"{style_block}"
        # Layer 5 — Entity graph
        f"{entity_block}"
        # Layer 6 — Grounding reminder + response rules
        f"\nGROUNDING REMINDER: Only assert facts from YOUR MEMORIES above. Do not infer or fabricate."
        f"\nRESPONSE RULES: Reply in 1-3 sentences. No lists. No formatting. No outside knowledge."
    )
    logger.debug("system prompt length: %d chars", len(prompt))
    return prompt
