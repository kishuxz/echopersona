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
  readiness_status?: 'pending' | 'processing' | 'ready' | 'failed';
}

export interface PersonaReadiness {
  ready: boolean;
  status: 'pending' | 'processing' | 'ready' | 'failed';
  sources_done: number;
  sources_total: number;
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
  plan_tier: 'free' | 'creator' | 'legacy' | 'preservation';
  status: 'active' | 'trialing' | 'past_due' | 'canceled' | 'unpaid' | null;
  can_use_chat: boolean;
  can_use_voice: boolean;
  can_use_video: boolean;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
  family_member_limit: number | null;  // null = unlimited
  is_preservation_locked: boolean;
}

export interface PersonaAccess {
  persona_id: string;
  can_use_chat: boolean;
  can_use_voice: boolean;
  can_use_video: boolean;
  can_add_family_member: boolean;
  family_member_limit: number | null;
  family_member_count: number;
  answer_count: number;
  is_preservation_locked: boolean;
  voice_id_present: boolean;
}

export interface CreationSession {
  session_id: string;
  persona_id: string;
  user_id: string;
  completed_question_ids: string[];
  current_question_id: string | null;
  pending_source_ids: string[];
  answers_per_category: Record<string, number>;
}

export interface NextStep {
  action: "ask_probe" | "steer" | "advance" | "done";
  prompt: string | null;
  question_id: string | null;
  probe_id: string | null;
  question_prompt: string | null;
  question_category: string | null;
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

export type ChatMode = "text" | "voice" | "video";

export interface ModeNegotiatedMessage {
  type: "mode_negotiated";
  mode: ChatMode;
  requested: ChatMode;
  reason?: string;
}

export interface VideoReadyMessage {
  type: "video_ready";
  url: string;
}

export interface VideoErrorMessage {
  type: "video_error";
  message: string;
}

export type ServerMessage =
  | { type: "transcript"; text: string; is_final: boolean; latency_ms: number }
  | { type: "llm_token"; token: string; latency_ms: number }
  | { type: "audio_chunk"; data: string; latency_ms?: number }
  | { type: "audio_end" }
  | VideoReadyMessage
  | VideoErrorMessage
  | ModeNegotiatedMessage
  | { type: "sentence_end" }
  | ({ type: "latency_summary" } & Omit<LatencySnapshot, "timestamp">)
  | { type: "error"; message: string }
  | { type: "pong" };

// ── Admin panel types ─────────────────────────────────────────────────────────

export interface AdminStats {
  total_personas: number;
  by_readiness: Record<string, number>;
  total_users: number;
  total_memory_units: number;
  total_relationships: number;
  plan_tier_counts: Record<string, number>;
}

export interface AdminPersonaRow {
  id: string;
  name: string;
  readiness_status: string;
  owner_email: string;
  plan_tier: string;
  memory_unit_count: number;
  relationship_count: number;
  created_at: string | null;
}

export interface AdminMemoryUnit {
  unit_id: string;
  content_first_person: string;
  memory_category: string;
  verified: boolean;
  fidelity_score: number;
  captured_at: string | null;
}

export interface AdminRelationship {
  id: string;
  listener_user_id: string;
  listener_email: string;
  entity_canonical: string;
  relationship: string;
  address_term: string;
  invite_id: string | null;
  created_at: string | null;
}

export interface AdminPersonaDetail {
  id: string;
  name: string;
  user_id: string;
  readiness_status: string;
  owner_email: string;
  plan_tier: string;
  tone: string;
  avoid_phrases: string[];
  answer_length_pref: string;
  tavus_replica_id: string | null;
  voice_card: Record<string, unknown>;
  identity_card: Record<string, unknown>;
  created_at: string | null;
  recent_memory_units: AdminMemoryUnit[];
  relationships: AdminRelationship[];
}

export interface AdminRelationshipCreate {
  listener_user_id: string;
  entity_canonical: string;
  relationship: string;
  address_term?: string;
}

export interface ReEnrichResponse {
  job_id: string | null;
  persona_id: string;
}
