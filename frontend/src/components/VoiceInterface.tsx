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
  personaTraits?: string[];
  storyCount?: number;
  idleVideoUrl?: string | null;
  avatarUrl?: string | null;
  onLatencyUpdate: (latency: LatencySnapshot) => void;
}

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
    <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-widest text-muted">
      {STAGES.map((s, i) => {
        const isActive   = s.key === stage;
        const isDone     = activeIndex > i && stage !== "idle";
        const isIdle     = stage === "idle" && i < STAGES.length - 1;
        const isComplete = isDone || isIdle;
        return (
          <div key={s.key} className="flex items-center gap-1.5">
            {i > 0 && (
              <span className={`transition-colors duration-300 ${isComplete || isActive ? "text-green/40" : "text-muted/30"}`}>→</span>
            )}
            <span className={`flex items-center gap-0.5 transition-colors duration-200 ${
              isActive ? "text-green" : isComplete ? "text-muted" : "text-muted/40"
            }`}>
              {isComplete ? (
                <span className="mr-0.5 text-green/60">✓</span>
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

export function VoiceInterface({
  sessionId,
  personaId,
  personaName,
  personaTraits = [],
  storyCount = 0,
  idleVideoUrl,
  avatarUrl,
  onLatencyUpdate,
}: VoiceInterfaceProps) {
  const { connect, sendJson, sendBinary } = useWebSocket();

  const [items, setItems]               = useState<TranscriptItem[]>([]);
  const [stage, setStage]               = useState<Stage>("idle");
  const [connected, setConnected]       = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isRecording, setIsRecording]   = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [videoUrl, setVideoUrl]         = useState<string | null>(null);
  const [videoLoading, setVideoLoading] = useState(false);
  const [lastResponseMs, setLastResponseMs] = useState<number | null>(null);
  const videoRef       = useRef<HTMLVideoElement>(null);
  const isRecordingRef = useRef(false);

  // Latency tracing refs
  const turnStartRef         = useRef<number>(0);
  const firstTokenLoggedRef  = useRef<boolean>(false);
  const firstAudioLoggedRef  = useRef<boolean>(false);

  // Playback
  const playbackCtxRef    = useRef<AudioContext | null>(null);
  const sentenceChunksRef = useRef<Uint8Array[]>([]);
  const nextPlayAtRef     = useRef<number>(0);
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
    } catch (e) {
      console.error("[AUDIO] decodeAudioData failed:", e);
    }
  }

  const doConnect = async (retryCount = 0) => {
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

      // Auto-retry once on unexpected close during initial connection
      if (retryCount === 0 && e.code !== 1000) {
        console.log("[WS] retrying in 1s...");
        setTimeout(() => {
          setIsConnecting(true);
          doConnect(1);
        }, 1000);
      }
    };

    ws.onmessage = async (event) => {
      const message = JSON.parse(event.data);

      if (message.type === "transcript") {
        const now = Date.now();
        turnStartRef.current        = now;
        firstTokenLoggedRef.current = false;
        firstAudioLoggedRef.current = false;
        setStage("LLM");
        setVideoLoading(true);
        setItems((current) => [...current, { role: "user", text: message.text }]);
        sentenceChunksRef.current = [];
        nextPlayAtRef.current     = 0;
        playbackLockRef.current   = Promise.resolve();
      }

      if (message.type === "video_ready") {
        setVideoUrl(message.url);
        setVideoLoading(false);
      }

      if (message.type === "llm_token") {
        if (!firstTokenLoggedRef.current) {
          firstTokenLoggedRef.current = true;
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
        }
        receiveChunk(message.data);
      }

      if (message.type === "sentence_end") {
        playbackLockRef.current = playbackLockRef.current.then(() => playSentence());
        await playbackLockRef.current;
      }

      if (message.type === "audio_end") {
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
        setLastResponseMs(message.total_ms);
        setStage("idle");
        onLatencyUpdate({ timestamp: Date.now(), ...message });
      }
    };
  };

  const handleConnect = async () => {
    if (isConnecting) return;
    setIsConnecting(true);
    setIsProcessing(false);
    setIsRecording(false);
    isRecordingRef.current    = false;
    sentenceChunksRef.current = [];
    nextPlayAtRef.current     = 0;

    // 500ms delay before first connect to avoid race on page load
    await new Promise((r) => setTimeout(r, 500));
    doConnect(0);
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

  const micBg = isProcessing ? "#2563EB" : isRecording ? "#16A34A" : "#18181B";

  return (
    <div className="flex flex-col gap-0 overflow-hidden rounded-2xl border border-border bg-surface shadow-card lg:flex-row" style={{ minHeight: '520px' }}>

      {/* ── LEFT PANEL — Avatar + Controls (40%) ── */}
      <div className="flex flex-col items-center gap-5 border-b border-border bg-elevated p-6 lg:w-[40%] lg:border-b-0 lg:border-r">

        {/* Portrait avatar */}
        <div className="relative w-full max-w-[260px] overflow-hidden rounded-2xl shadow-card-hover" style={{ aspectRatio: '3/4' }}>
          {/* D-ID response video */}
          {videoUrl && (
            <video
              ref={videoRef}
              src={videoUrl}
              className="h-full w-full object-cover"
              autoPlay
              playsInline
              muted={false}
              onEnded={() => setVideoUrl(null)}
              onError={(e) => console.error("[VIDEO] playback error:", e)}
            />
          )}

          {/* Idle loop video */}
          {!videoUrl && idleVideoUrl && (
            <video
              src={idleVideoUrl}
              className="h-full w-full object-cover"
              autoPlay
              loop
              playsInline
              muted
            />
          )}

          {/* Static avatar photo */}
          {!videoUrl && !idleVideoUrl && avatarUrl && (
            <img
              src={avatarUrl}
              alt={personaName ?? "Persona"}
              className="h-full w-full object-cover"
              style={{ filter: 'blur(0px)' }}
            />
          )}

          {/* Letter / spinner placeholder */}
          {!videoUrl && !idleVideoUrl && !avatarUrl && (
            <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-cream to-elevated">
              {videoLoading ? (
                <svg className="h-8 w-8 animate-spin text-green" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" />
                  <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <span className="font-fraunces text-6xl font-semibold text-text/20">
                  {personaName?.[0]?.toUpperCase() ?? "?"}
                </span>
              )}
            </div>
          )}

          {/* Live indicator overlay */}
          {connected && (
            <div className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-black/40 px-2.5 py-1 backdrop-blur-sm">
              <span
                className="h-1.5 w-1.5 rounded-full bg-green"
                style={{ animation: "blink 1s step-end infinite" }}
              />
              <span className="font-sans text-[10px] font-medium text-white">Live</span>
            </div>
          )}
        </div>

        {/* Persona name + traits */}
        {personaName && (
          <div className="w-full max-w-[260px] text-center">
            <h3 className="font-fraunces text-xl font-semibold text-text">{personaName}</h3>
            {personaTraits.length > 0 && (
              <div className="mt-2 flex flex-wrap justify-center gap-1.5">
                {personaTraits.slice(0, 3).map((t) => (
                  <span key={t} className="rounded-full bg-cream px-2.5 py-0.5 font-sans text-[10px] text-textdim">
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Controls */}
        <div className="flex w-full max-w-[260px] flex-col items-center gap-4">
          {!connected ? (
            <button
              className="w-full rounded-xl bg-accent py-3 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
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
              <p className="font-sans text-[11px] text-muted">
                {isProcessing ? "Processing…" : isRecording ? "Listening…" : "Hold to speak"}
              </p>

              {/* Mic button */}
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
                  className={`relative z-10 flex h-20 w-20 items-center justify-center rounded-full transition-all duration-150 ${isRecording ? "scale-105" : ""}`}
                  style={{ backgroundColor: micBg, cursor: isProcessing ? "not-allowed" : "pointer" }}
                >
                  {isProcessing ? (
                    <svg className="h-6 w-6 animate-spin text-white" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                      <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-7 w-7">
                      <rect x="9" y="2" width="6" height="12" rx="3" />
                      <path d="M5 10a7 7 0 0014 0" />
                      <line x1="12" y1="19" x2="12" y2="23" />
                      <line x1="8"  y1="23" x2="16" y2="23" />
                    </svg>
                  )}
                </button>
              </div>

              {/* Waveform */}
              {isRecording && (
                <div className="flex items-center gap-0.5">
                  {Array.from({ length: 14 }).map((_, i) => (
                    <span key={i} className="wave-bar" style={{ animationDelay: `${i * 45}ms` }} />
                  ))}
                </div>
              )}

              {/* Pipeline status */}
              <PipelineBar stage={stage} />
            </>
          )}
        </div>
      </div>

      {/* ── RIGHT PANEL — Conversation (60%) ── */}
      <div className="flex flex-1 flex-col lg:w-[60%]">
        <ConversationLog
          items={items}
          draft=""
          personaName={personaName}
          lastResponseMs={lastResponseMs}
          hasVoice={Boolean(personaId)}
          storyCount={storyCount}
        />
      </div>
    </div>
  );
}
