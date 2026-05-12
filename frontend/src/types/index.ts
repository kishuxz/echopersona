export interface LatencySnapshot {
  timestamp: number;
  stt_ms: number;
  llm_first_token_ms: number;
  tts_first_audio_ms: number;
  total_ms: number;
}

export interface TranscriptItem {
  role: "user" | "assistant";
  text: string;
}

export interface PersonaCreate {
  name: string;
  stories: string[];
  personality_traits: string[];
  speaking_style: string;
}

export interface Persona extends PersonaCreate {
  id: string;
  user_id: string;
  voice_id?: string | null;
  did_avatar_url?: string | null;
  created_at?: string;
}

export type ServerMessage =
  | { type: "transcript"; text: string; is_final: boolean; latency_ms: number }
  | { type: "llm_token"; token: string; latency_ms: number }
  | { type: "audio_chunk"; data: string; latency_ms?: number }
  | { type: "audio_end" }
  | { type: "video_ready"; url: string }
  | { type: "sentence_end" }
  | ({ type: "latency_summary" } & Omit<LatencySnapshot, "timestamp">)
  | { type: "error"; message: string }
  | { type: "pong" };
