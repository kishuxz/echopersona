"""Persona RAG: embed memory_units, FAISS retrieval, system-prompt builder.

Index priority for a persona:
  1. memory_units from Supabase (Stage 1-2 pipeline output, richer content)
  2. persona.stories (legacy fallback for personas that pre-date the pipeline)

retrieve() returns list[dict] — always has "text" key, may have:
  stance, themes, entities  (when built from memory_units)
"""
import logging

import numpy as np

from config import settings
from models.consent import ListenerContext
from models.persona import Persona, PersonaCreate

logger = logging.getLogger(__name__)

_EMBED_MODEL = "paraphrase-MiniLM-L3-v2"


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

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        """Return top-k matching units as dicts with at least a 'text' key."""
        if not self._units:
            return []

        if self.index is None or settings.mock_mode:
            # Keyword fallback
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
            _, idxs = self.index.search(q_emb, top_k)
            return [self._units[i] for i in idxs[0] if 0 <= i < len(self._units)]
        except Exception:
            norms = np.linalg.norm(q_emb, axis=1, keepdims=True)
            q_emb = q_emb / np.maximum(norms, 1e-12)
            scores = np.asarray(self.index) @ q_emb[0]
            idxs = np.argsort(scores)[::-1][:top_k]
            return [self._units[int(i)] for i in idxs]


# ── process-level cache ─────────────────────────────────────────────────────

PERSONAS: dict[str, Persona] = {}
RAG_INDICES: dict[str, PersonaRAG] = {}


# ── system prompt ───────────────────────────────────────────────────────────

def _truncate(text: str, max_words: int = 80) -> str:
    words = text.split()
    return " ".join(words[:max_words])


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
    memory_lines = [_truncate(u["text"]) for u in units] if units else []
    if memory_lines:
        context_block = "\n".join(f"- {m}" for m in memory_lines)
        no_memory_fallback = ""
    else:
        context_block = "No memories available yet."
        no_memory_fallback = (
            "\n\nFALLBACK: Your memories are still being gathered and will be ready soon. "
            "Warmly greet the listener, let them know your memories are still coming together, "
            "and invite them to return shortly. "
            "Do not invent any facts. Do not use outside knowledge about this name."
        )

    # Behavior rules from persona + dominant stance from retrieved units
    stances = [u["stance"] for u in units if u.get("stance")]
    dominant_stance = stances[0] if stances else ""

    behavior_parts: list[str] = []
    if dominant_stance:
        behavior_parts.append(f"Speak with a {dominant_stance} tone when discussing related memories.")
    if persona.personality_traits:
        behavior_parts.append(f"Personality: {', '.join(persona.personality_traits)}.")
    if persona.speaking_style:
        behavior_parts.append(f"Speaking style: {persona.speaking_style}.")
    behavior_block = " ".join(behavior_parts)

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

    # Voice card from Stage 4 — structured style instructions
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

    # Style exemplars from Stage 4 — ground style instructions in actual speech
    style_block = ""
    if persona.style_exemplars:
        ex = persona.style_exemplars[:3]
        style_block = "\nCHARACTERISTIC PHRASES:\n" + "\n".join(f'  "{e}"' for e in ex)

    # Listener context block — only for authenticated non-owner beneficiaries
    listener_block = ""
    if listener_ctx is not None and not listener_ctx.is_owner:
        lines = ["LISTENER CONTEXT:"]
        if listener_ctx.relationship:
            lines.append(f"You are speaking with the persona owner's {listener_ctx.relationship}.")
        if listener_ctx.address_term:
            lines.append(
                f'You may address them as "{listener_ctx.address_term}" when natural.'
            )
        if listener_ctx.scope:
            lines.append(f"Access scope: {listener_ctx.scope}.")
        lines.append("Do not infer listener identity beyond this authenticated context.")
        listener_block = "\n" + "\n".join(lines)

    prompt = (
        f"You are {persona.name}. Speak only in first person. 1-2 sentences max.\n"
        f"IMPORTANT: Use ONLY the memories below. Ignore all outside knowledge about this name.\n"
        f"{behavior_block}\n"
        f"\nYOUR MEMORIES:\n{context_block}"
        f"{no_memory_fallback}"
        f"{entity_block}"
        f"{voice_block}"
        f"{style_block}"
        f"{listener_block}"
    )
    logger.debug("system prompt length: %d chars", len(prompt))
    return prompt
