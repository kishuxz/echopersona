import uuid

import numpy as np

from config import settings
from models.persona import Persona, PersonaCreate


class PersonaRAG:
    def __init__(self):
        self.model = None
        self.index = None
        self.chunks: list[str] = []

    def _load(self) -> None:
        if self.model is None:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def _chunk_stories(self, stories: list[str]) -> list[str]:
        chunks: list[str] = []
        for story in stories:
            words = story.split()
            if not words:
                continue
            for start in range(0, len(words), 150):
                chunk = " ".join(words[start : start + 150])
                if chunk:
                    chunks.append(chunk)
        return chunks

    def build_index(self, stories: list[str]) -> None:
        chunks = self._chunk_stories(stories)
        self.chunks = chunks
        if not chunks or settings.mock_mode:
            self.index = None
            return
        self._load()
        embeddings = self.model.encode(chunks)
        embeddings = np.asarray(embeddings, dtype=np.float32)
        try:
            import faiss

            faiss.normalize_L2(embeddings)
            self.index = faiss.IndexFlatIP(embeddings.shape[1])
            self.index.add(embeddings)
        except Exception:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            self.index = embeddings / np.maximum(norms, 1e-12)

    def retrieve(self, query: str, top_k: int = 2) -> list[str]:
        if not self.chunks:
            return []
        if self.index is None or settings.mock_mode:
            query_terms = set(query.lower().split())
            scored = [
                (len(query_terms.intersection(chunk.lower().split())), chunk)
                for chunk in self.chunks
            ]
            return [chunk for score, chunk in sorted(scored, reverse=True)[:top_k] if score > 0] or self.chunks[:top_k]
        self._load()

        query_embedding = np.asarray(self.model.encode([query]), dtype=np.float32)
        try:
            import faiss

            faiss.normalize_L2(query_embedding)
            _distances, indices = self.index.search(query_embedding, top_k)
            return [self.chunks[i] for i in indices[0] if 0 <= i < len(self.chunks)]
        except Exception:
            norms = np.linalg.norm(query_embedding, axis=1, keepdims=True)
            query_embedding = query_embedding / np.maximum(norms, 1e-12)
            scores = np.asarray(self.index) @ query_embedding[0]
            indices = np.argsort(scores)[::-1][:top_k]
            return [self.chunks[int(i)] for i in indices]


PERSONAS: dict[str, Persona] = {}
RAG_INDICES: dict[str, PersonaRAG] = {}


def create_persona(payload: PersonaCreate) -> Persona:
    persona_id = str(uuid.uuid4())
    persona = Persona(id=persona_id, **payload.model_dump())
    rag = PersonaRAG()
    rag.build_index(payload.stories)
    PERSONAS[persona_id] = persona
    RAG_INDICES[persona_id] = rag
    return persona


def build_system_prompt(persona: Persona | None, retrieved_context: list[str]) -> str:
    if persona is None:
        return (
            "You are a helpful AI having a voice conversation. "
            "Answer naturally in 1-2 short sentences. Never use lists or formatting."
        )

    def _truncate(text: str, max_words: int = 100) -> str:
        words = text.split()
        return " ".join(words[:max_words])

    context_block = "\n".join(_truncate(c) for c in retrieved_context) if retrieved_context else "No memories available."
    extras = ""
    if persona.personality_traits:
        extras += f"\nPERSONALITY: {', '.join(persona.personality_traits)}"
    if persona.speaking_style:
        extras += f"\nSTYLE: {persona.speaking_style}"

    prompt = (
        f"You are {persona.name}. Speak only in first person. 2 sentences max.\n"
        f"IMPORTANT: Use ONLY the memories below. Ignore all outside knowledge about this name.\n"
        f"\nYOUR MEMORIES:\n{context_block}"
        f"{extras}"
    )
    print(f"[PROMPT] length: {len(prompt)} chars")
    return prompt
