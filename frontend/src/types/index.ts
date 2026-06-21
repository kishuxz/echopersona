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
  idle_video_url?: string | null;
  simli_face_id?: string | null;
  created_at?: string;
}

export interface ModalityConsent {
  text_twin: boolean;
  voice_clone: boolean;
  video_avatar: boolean;
}

export interface ConsentRights {
  subject_may_review: boolean;
  subject_may_delete: boolean;
}

export interface ConsentRecord {
  id: string;
  persona_id: string;
  subject_user_id: string;
  captured_at: string;
  consent_version: number;
  status: "active" | "superseded" | "revoked";
  ended_at: string | null;
  supersedes: string | null;
  modality_consent: ModalityConsent;
  rights: ConsentRights;
  policy_version: string;
  affirmation_media_ref: string | null;
}

export interface ConsentCreate {
  modality_consent?: Partial<ModalityConsent>;
  rights?: Partial<ConsentRights>;
  policy_version?: string;
  affirmation_media_ref?: string | null;
}

export interface Beneficiary {
  user_id: string;
  relationship: string;
  scope: "full" | "curated";
  activation_trigger: "immediate" | "posthumous_verified";
  address_term?: string;
  closeness_level?: number | null;
  greeting_style?: string;
  release_messages?: string[];
}

export interface SuccessionRecord {
  id: string;
  persona_id: string;
  subject_user_id: string;
  captured_at: string;
  status: "active" | "superseded" | "revoked";
  ended_at: string | null;
  supersedes: string | null;
  beneficiaries: Beneficiary[];
}

export interface SuccessionCreate {
  beneficiaries?: Beneficiary[];
}

export interface BillingStatus {
  plan_tier: 'free' | 'creator' | 'legacy';
  status: 'active' | 'trialing' | 'past_due' | 'canceled' | 'unpaid' | null;
  can_use_chat: boolean;
  can_use_voice: boolean;
  can_use_video: boolean;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
}

export interface CreationSession {
  session_id: string;
  persona_id: string;
  user_id: string;
  completed_question_ids: string[];
  current_question_id: string | null;
  pending_source_ids: string[];
}

export interface NextStep {
  action: "ask_probe" | "steer" | "advance" | "done";
  prompt: string | null;
  question_id: string | null;
  probe_id: string | null;
  question_prompt: string | null;
  session: CreationSession;
}

export interface StartSessionResponse {
  session: CreationSession;
  next_step: NextStep;
}

export interface CaptureResponse {
  source_id: string;
  answer_text: string;
  next_step: NextStep;
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
