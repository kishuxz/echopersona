import { useRef, useState } from "react";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { useWebSocket } from "../hooks/useWebSocket";
import { buildWsUrl } from "../lib/api";
import type { LatencySnapshot, TranscriptItem } from "../types";
import { ConversationLog } from "./ConversationLog";

interface VoiceInterfaceProps {
  sessionId: string;
  personaId?: string;
  personaName?: string;
  idleVideoUrl?: string | null;
  onLatencyUpdate: (latency: LatencySnapshot) => void;
}

// ── Pipeline stage display ─────────────────────────────────────────────────
type Stage = "idle" | "recording" | "STT" | "LLM" | "TTS";
const STAGES: { key: Stage; label: string }[] = [
  { key: "STT",       label: "STT" },
  { key: "LLM",       label: "LLM" },
  { key: "TTS",       label: "TTS" },
  { key: "idle",      label: "DONE" },
];

function PipelineBar({ stage }: { stage: Stage }) {
  const activeIndex = STAGES.findIndex((s) => s.key === stage);
  return (
    <div className="flex items-center gap-1 font-mono text-[10px]">
      {STAGES.map((s, i) => {
        const isActive = s.key === stage;
        const isDone   = activeIndex > i && stage !== "idle";
        const isIdle   = stage === "idle" && i < STAGES.length - 1;
        return (
          <div key={s.key} className="flex items-center gap-1">
            {i > 0 && <span className="text-muted">→</span>}
            <span
              className={
                isActive
                  ? "text-green"
                  : isDone || isIdle
                  ? "text-textdim"
                  : "text-muted"
              }
            >
              {isDone || (stage === "idle" && s.key !== "idle") ? "✓" : ""}{s.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────
export function VoiceInterface({ sessionId, personaId, personaName, idleVideoUrl, onLatencyUpdate }: VoiceInterfaceProps) {
  const { connect, sendJson, sendBinary } = useWebSocket();

  const [items, setItems]               = useState<TranscriptItem[]>([]);
  const [stage, setStage]               = useState<Stage>("idle");
  const [connected, setConnected]       = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isRecording, setIsRecording]   = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [videoUrl, setVideoUrl]         = useState<string | null>(null);
  const [videoLoading, setVideoLoading] = useState(false);
  const videoRef       = useRef<HTMLVideoElement>(null);
  const isRecordingRef = useRef(false);

  // Latency tracing refs — reset each turn
  const turnStartRef         = useRef<number>(0);
  const firstTokenLoggedRef  = useRef<boolean>(false);
  const firstAudioLoggedRef  = useRef<boolean>(false);

  // Playback — lazy AudioContext, per-sentence chunk buffer, gapless scheduler
  const playbackCtxRef    = useRef<AudioContext | null>(null);
  const sentenceChunksRef = useRef<Uint8Array[]>([]);
  const nextPlayAtRef     = useRef<number>(0);
  // Serialise playSentence calls so s2 chunks can't be decoded before s1 finishes
  const playbackLockRef   = useRef<Promise<void>>(Promise.resolve());

  function receiveChunk(base64data: string) {
    const binary = atob(base64data);
    const bytes  = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    sentenceChunksRef.current.push(bytes);
  }

  async function playSentence() {
    if (sentenceChunksRef.current.length === 0) return;
    if (!playbackCtxRef.current) playbackCtxRef.current = new AudioContext();
    const ctx = playbackCtxRef.current;
    if (ctx.state === "suspended") await ctx.resume();

    const totalBytes = sentenceChunksRef.current.reduce((s, a) => s + a.length, 0);
    const combined   = new Uint8Array(totalBytes);
    let offset = 0;
    for (const chunk of sentenceChunksRef.current) { combined.set(chunk, offset); offset += chunk.length; }
    sentenceChunksRef.current = [];

    try {
      const audioBuffer = await ctx.decodeAudioData(combined.buffer);
      const source      = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      const startAt = Math.max(nextPlayAtRef.current, ctx.currentTime);
      source.start(startAt);
      nextPlayAtRef.current = startAt + audioBuffer.duration;
      console.log("[AUDIO] sentence scheduled, duration:", audioBuffer.duration.toFixed(2), "s");
    } catch (e) {
      console.error("[AUDIO] decodeAudioData failed:", e);
    }
  }

  const handleConnect = async () => {
    if (isConnecting) return;
    setIsConnecting(true);
    setIsProcessing(false);
    setIsRecording(false);
    isRecordingRef.current    = false;
    sentenceChunksRef.current = [];
    nextPlayAtRef.current     = 0;

    let wsUrl: string;
    try {
      wsUrl = personaId
        ? await buildWsUrl(sessionId, personaId)
        : `${import.meta.env.VITE_WS_BASE_URL ?? 'ws://localhost:8000'}/ws/${sessionId}`;
    } catch (e) {
      console.error("[WS] failed to build URL:", e);
      setIsConnecting(false);
      return;
    }
    const ws = connect(wsUrl);
    if (!ws) { setIsConnecting(false); return; }

    ws.onopen = () => {
      console.log("[WS] connected");
      setConnected(true);
      setIsConnecting(false);
      setIsProcessing(false);
      setIsRecording(false);
    };

    ws.onclose = (e) => {
      console.log("[WS] closed", e.code, e.reason);
      setConnected(false);
      setIsConnecting(false);
      setIsProcessing(false);
      setIsRecording(false);
      isRecordingRef.current = false;
    };

    ws.onmessage = async (event) => {
      const message = JSON.parse(event.data);
      console.log("[WS] message received:", message.type, Object.keys(message));

      if (message.type === "transcript") {
        const now = Date.now();
        turnStartRef.current        = now;
        firstTokenLoggedRef.current = false;
        firstAudioLoggedRef.current = false;
        console.log(`[${now}] STT transcript received: "${message.text}" | stt_latency=${message.latency_ms}ms`);
        setStage("LLM");
        setVideoLoading(true);
        setItems((current) => [...current, { role: "user", text: message.text }]);
        sentenceChunksRef.current = [];
        nextPlayAtRef.current     = 0;
        playbackLockRef.current   = Promise.resolve();
      }

      if (message.type === "video_ready") {
        console.log("[VIDEO] video_ready:", message.url);
        setVideoUrl(message.url);
        setVideoLoading(false);
      }

      if (message.type === "llm_token") {
        if (!firstTokenLoggedRef.current) {
          firstTokenLoggedRef.current = true;
          console.log(`[${Date.now()}] First LLM token | since transcript: ${Date.now() - turnStartRef.current}ms`);
        }
        setStage("TTS");
        setItems((current) => {
          const last = current[current.length - 1];
          if (last?.role === "assistant")
            return [...current.slice(0, -1), { role: "assistant", text: last.text + message.token }];
          return [...current, { role: "assistant", text: message.token }];
        });
      }

      if (message.type === "audio_chunk") {
        if (!firstAudioLoggedRef.current) {
          firstAudioLoggedRef.current = true;
          console.log(`[${Date.now()}] First audio chunk | since transcript: ${Date.now() - turnStartRef.current}ms`);
        }
        receiveChunk(message.data);
      }

      if (message.type === "sentence_end") {
        console.log("[AUDIO] sentence_end — scheduling sentence playback");
        playbackLockRef.current = playbackLockRef.current.then(() => playSentence());
        await playbackLockRef.current;
      }

      if (message.type === "audio_end") {
        console.log("[AUDIO] audio_end — flushing final sentence");
        playbackLockRef.current = playbackLockRef.current.then(() => playSentence());
        await playbackLockRef.current;
        setIsProcessing(false);
        setIsRecording(false);
        setStage("idle");
      }

      if (message.type === "error") {
        console.error("[WS] server error:", message.message);
        setIsProcessing(false);
      }

      if (message.type === "latency_summary") {
        console.log(
          `[${Date.now()}] Latency summary | STT=${message.stt_ms}ms | LLM=${message.llm_first_token_ms}ms | TTS=${message.tts_first_audio_ms}ms | Total=${message.total_ms}ms`,
        );
        setStage("idle");
        onLatencyUpdate({ timestamp: Date.now(), ...message });
      }
    };
  };

  const recorder = useAudioRecorder((pcm) => sendBinary(pcm));

  const handleMicMouseDown = async () => {
    if (isRecordingRef.current || isProcessing) return;
    isRecordingRef.current = true;
    setIsRecording(true);
    setStage("recording");
    try {
      await recorder.start();
    } catch (e) {
      console.error("[MIC] recorder.start() failed:", e);
      isRecordingRef.current = false;
      setIsRecording(false);
      setStage("idle");
    }
  };

  const handleMicMouseUp = () => {
    if (!isRecordingRef.current) return;
    isRecordingRef.current = false;
    setIsRecording(false);
    setIsProcessing(true);
    recorder.stop();
    sendJson({ type: "audio_end" });
    setStage("STT");
  };

  console.log("[STATE] isRecording:", isRecording, "isProcessing:", isProcessing, "connected:", connected);

  // ── Derived UI state ──────────────────────────────────────────────────
  const micBorderColor = isProcessing ? "#00aaff" : isRecording ? "#00ff88" : "#1e1e1e";
  const micBgColor     = isProcessing ? "rgba(0,170,255,0.05)" : isRecording ? "rgba(0,255,136,0.08)" : "#111111";
  const micIconColor   = isProcessing ? "#00aaff" : isRecording ? "#00ff88" : "#444444";

  return (
    <div className="flex flex-col gap-4 lg:flex-row">

      {/* ── Voice control panel ── */}
      <div className="flex min-h-[280px] flex-col items-center gap-5 rounded-lg border border-border bg-surface p-6 lg:w-64 lg:flex-shrink-0">

        {/* Avatar / video display — priority: response video > idle loop > placeholder */}
        <div className="flex flex-col items-center gap-2">

          {/* 1. D-ID response video — shown when video_ready arrives; returns to idle on end */}
          {videoUrl && (
            <video
              ref={videoRef}
              src={videoUrl}
              className="h-32 w-32 rounded-full border-2 border-green object-cover"
              autoPlay
              playsInline
              muted={false}
              onEnded={() => setVideoUrl(null)}
              onError={(e) => console.error("[VIDEO] playback error:", e)}
            />
          )}

          {/* 2. Idle loop — plays while waiting for a response video */}
          {!videoUrl && idleVideoUrl && (
            <video
              src={idleVideoUrl}
              className="h-32 w-32 rounded-full border-2 border-green object-cover"
              autoPlay
              loop
              playsInline
              muted
            />
          )}

          {/* 3. Letter / spinner placeholder */}
          {!videoUrl && !idleVideoUrl && (
            <div
              className="flex h-32 w-32 items-center justify-center rounded-full border-2 bg-surface"
              style={{ borderColor: connected ? "#00ff88" : "#1e1e1e" }}
            >
              {videoLoading ? (
                <svg className="h-6 w-6 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="#00ff88" strokeWidth="3" />
                  <path className="opacity-80" fill="#00ff88" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <span className="font-mono text-2xl font-bold text-textdim">
                  {personaName?.[0]?.toUpperCase() ?? "?"}
                </span>
              )}
            </div>
          )}

          {videoLoading && !videoUrl && !idleVideoUrl && connected && (
            <p className="font-mono text-[9px] uppercase tracking-widest text-textdim">
              generating video…
            </p>
          )}
        </div>

        {/* Connection status */}
        <div className="flex w-full items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-widest text-textdim">Voice</span>
          <div className="flex items-center gap-1.5">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{
                background: connected ? "#00ff88" : "#444",
                animation: connected ? "blink 1s step-end infinite" : "none",
              }}
            />
            <span
              className="font-mono text-[10px] uppercase"
              style={{ color: connected ? "#00ff88" : "#444" }}
            >
              {connected ? "Connected" : "Offline"}
            </span>
          </div>
        </div>

        {/* Mic button area */}
        {!connected ? (
          <button
            className="w-full rounded-lg border border-green bg-green py-3 font-mono text-sm font-bold uppercase tracking-widest text-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={handleConnect}
            disabled={isConnecting}
          >
            {isConnecting ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Connecting…
              </span>
            ) : (
              "Start Session"
            )}
          </button>
        ) : (
          <>
            {/* Instruction text */}
            <p
              className="font-mono text-xs uppercase tracking-widest transition-colors"
              style={{
                color: isProcessing ? "#00aaff" : isRecording ? "#00ff88" : "#888",
              }}
            >
              {isProcessing ? "Processing…" : isRecording ? "Listening…" : "Hold to speak"}
            </p>

            {/* Mic button with pulse ring */}
            <div className="relative flex items-center justify-center">
              {isRecording && (
                <div
                  className="absolute h-24 w-24 rounded-full border border-green"
                  style={{ animation: "ping-ring 1.2s ease-out infinite" }}
                />
              )}

              <button
                onMouseDown={handleMicMouseDown}
                onMouseUp={handleMicMouseUp}
                onMouseLeave={handleMicMouseUp}
                onTouchStart={(e) => { e.preventDefault(); handleMicMouseDown(); }}
                onTouchEnd={(e)   => { e.preventDefault(); handleMicMouseUp(); }}
                disabled={isProcessing}
                className="relative z-10 flex h-20 w-20 items-center justify-center rounded-full border-2 transition-all duration-150"
                style={{
                  borderColor:     micBorderColor,
                  backgroundColor: micBgColor,
                  cursor: isProcessing ? "not-allowed" : "pointer",
                  boxShadow: isRecording
                    ? "0 0 20px rgba(0,255,136,0.2)"
                    : isProcessing
                    ? "0 0 20px rgba(0,170,255,0.2)"
                    : "none",
                }}
              >
                {isProcessing ? (
                  <svg className="h-6 w-6 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-20" cx="12" cy="12" r="10" stroke="#00aaff" strokeWidth="3" />
                    <path className="opacity-80" fill="#00aaff" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke={micIconColor}
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="h-7 w-7 transition-colors duration-150"
                  >
                    <rect x="9" y="2" width="6" height="12" rx="3" />
                    <path d="M5 10a7 7 0 0014 0" />
                    <line x1="12" y1="19" x2="12" y2="23" />
                    <line x1="8"  y1="23" x2="16" y2="23" />
                  </svg>
                )}
              </button>
            </div>

            {/* Waveform (recording) */}
            {isRecording && (
              <div className="flex items-center gap-0.5">
                {Array.from({ length: 18 }).map((_, i) => (
                  <span
                    key={i}
                    className="wave-bar"
                    style={{ animationDelay: `${i * 45}ms` }}
                  />
                ))}
              </div>
            )}

            {/* Pipeline bar */}
            <PipelineBar stage={stage} />
          </>
        )}
      </div>

      {/* ── Conversation log ── */}
      <div className="min-h-[280px] flex-1">
        <ConversationLog items={items} draft="" />
      </div>
    </div>
  );
}
