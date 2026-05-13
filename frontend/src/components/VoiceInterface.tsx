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
  { key: "STT",  label: "STT" },
  { key: "LLM",  label: "LLM" },
  { key: "TTS",  label: "TTS" },
  { key: "idle", label: "DONE" },
];

function PipelineBar({ stage }: { stage: Stage }) {
  const activeIndex = STAGES.findIndex((s) => s.key === stage);
  return (
    <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-widest">
      {STAGES.map((s, i) => {
        const isActive   = s.key === stage;
        const isDone     = activeIndex > i && stage !== "idle";
        const isIdle     = stage === "idle" && i < STAGES.length - 1;
        const isComplete = isDone || isIdle;
        return (
          <div key={s.key} className="flex items-center gap-1.5">
            {i > 0 && (
              <span className={`transition-colors duration-300 ${
                isComplete || isActive ? "text-green/20" : "text-[#1a1a1a]"
              }`}>→</span>
            )}
            <span className={`flex items-center gap-0.5 transition-colors duration-200 ${
              isActive ? "text-green" : isComplete ? "text-[#3a3a3a]" : "text-[#1e1e1e]"
            }`}>
              {isComplete ? (
                <span className="mr-0.5 text-green/40">✓</span>
              ) : isActive ? (
                <span className="blink mr-0.5">●</span>
              ) : (
                <span className="mr-0.5">○</span>
              )}
              {s.label}
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
  const micBorderColor = isProcessing ? "#0088ff" : isRecording ? "#00ff88" : "#1e1e1e";
  const micBgColor     = isProcessing ? "rgba(0,136,255,0.06)" : isRecording ? "rgba(0,255,136,0.1)" : "#0a0a0a";
  const micIconColor   = isProcessing ? "#0088ff" : isRecording ? "#00ff88" : "#2e2e2e";

  return (
    <div className="flex flex-col gap-4 lg:flex-row">

      {/* ── Voice control panel ── */}
      <div className="flex min-h-[340px] flex-col items-center gap-5 rounded-lg border border-[#1a1a1a] bg-[#0d0d0d] p-6 lg:w-64 lg:flex-shrink-0">

        {/* Avatar / video display */}
        <div className="flex flex-col items-center gap-2">
          <div className={`rounded-full ${
            isRecording ? "avatar-speaking" : connected ? "avatar-idle" : "avatar-disconnected"
          }`}>
            {/* 1. D-ID response video */}
            {videoUrl && (
              <video
                ref={videoRef}
                src={videoUrl}
                className="h-40 w-40 rounded-full object-cover"
                autoPlay
                playsInline
                muted={false}
                onEnded={() => setVideoUrl(null)}
                onError={(e) => console.error("[VIDEO] playback error:", e)}
              />
            )}

            {/* 2. Idle loop */}
            {!videoUrl && idleVideoUrl && (
              <video
                src={idleVideoUrl}
                className="h-40 w-40 rounded-full object-cover"
                autoPlay
                loop
                playsInline
                muted
              />
            )}

            {/* 3. Letter / spinner placeholder */}
            {!videoUrl && !idleVideoUrl && (
              <div className="flex h-40 w-40 items-center justify-center rounded-full bg-[#0a0a0a]">
                {videoLoading ? (
                  <svg className="h-7 w-7 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-20" cx="12" cy="12" r="10" stroke="#00ff88" strokeWidth="2.5" />
                    <path className="opacity-80" fill="#00ff88" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <span className="font-mono text-3xl font-bold text-[#222]">
                    {personaName?.[0]?.toUpperCase() ?? "?"}
                  </span>
                )}
              </div>
            )}
          </div>

          {videoLoading && !videoUrl && !idleVideoUrl && connected && (
            <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-[#2a2a2a]">
              generating video…
            </p>
          )}
        </div>

        {/* Connection status */}
        <div className="flex w-full items-center justify-between border-t border-[#151515] pt-3">
          <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-[#272727]">Status</span>
          <div className="flex items-center gap-1.5">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{
                background: connected ? "#00ff88" : "#252525",
                animation: connected ? "blink 1s step-end infinite" : "none",
              }}
            />
            <span
              className="font-mono text-[9px] uppercase tracking-widest"
              style={{ color: connected ? "#00ff88" : "#252525" }}
            >
              {connected ? "Live" : "Offline"}
            </span>
          </div>
        </div>

        {/* Mic button area */}
        {!connected ? (
          <button
            className="btn-glow-green w-full rounded border border-green bg-green py-3 font-mono text-sm font-bold uppercase tracking-widest text-[#001f0e] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
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
              className="font-mono text-[10px] uppercase tracking-[0.2em] transition-colors"
              style={{ color: isProcessing ? "#0088ff" : isRecording ? "#00ff88" : "#2e2e2e" }}
            >
              {isProcessing ? "Processing…" : isRecording ? "Listening…" : "Hold to speak"}
            </p>

            {/* Mic button with pulse ring */}
            <div className="relative flex items-center justify-center">
              {isRecording && (
                <div
                  className="absolute h-28 w-28 rounded-full border border-green/30"
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
                className="relative z-10 flex h-24 w-24 items-center justify-center rounded-full border-2 transition-all duration-150"
                style={{
                  borderColor:     micBorderColor,
                  backgroundColor: micBgColor,
                  cursor: isProcessing ? "not-allowed" : "pointer",
                  boxShadow: isRecording
                    ? "0 0 28px rgba(0,255,136,0.3), 0 0 0 1px rgba(0,255,136,0.2)"
                    : isProcessing
                    ? "0 0 24px rgba(0,136,255,0.25)"
                    : "none",
                }}
              >
                {isProcessing ? (
                  <svg className="h-7 w-7 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-20" cx="12" cy="12" r="10" stroke="#0088ff" strokeWidth="3" />
                    <path className="opacity-80" fill="#0088ff" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke={micIconColor}
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="h-8 w-8 transition-colors duration-150"
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
      <div className="min-h-[340px] flex-1">
        <ConversationLog items={items} draft="" />
      </div>
    </div>
  );
}
