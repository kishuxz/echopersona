// Fallback base URLs used when VITE_ env vars are absent
export const DEFAULT_API_BASE = 'http://localhost:8000'
export const DEFAULT_WS_BASE = 'ws://localhost:8000'

// Server → client WebSocket message types
export const WS_SERVER_MSG = {
  TRANSCRIPT: 'transcript',
  LLM_TOKEN: 'llm_token',
  AUDIO_CHUNK: 'audio_chunk',
  AUDIO_END: 'audio_end',
  SENTENCE_END: 'sentence_end',
  VIDEO_READY: 'video_ready',
  LATENCY_SUMMARY: 'latency_summary',
  ERROR: 'error',
  PONG: 'pong',
} as const

// Client → server WebSocket message types
export const WS_CLIENT_MSG = {
  AUDIO_END: 'audio_end',
  PING: 'ping',
  TEXT_TURN: 'text_turn',
  SIMLI_SESSION_REQUEST: 'simli_session_request',
} as const

// Timing
export const CONNECT_DELAY_MS = 500        // pause before initial WS connect to avoid page-load race
export const RECONNECT_DELAY_MS = 1000     // delay before auto-retry on unexpected close
export const KEEP_ALIVE_INTERVAL_MS = 10 * 60 * 1000  // Render free-tier keep-alive ping interval
