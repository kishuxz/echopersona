import { useEffect, useRef, useState } from "react";
import { CONNECT_DELAY_MS, DEFAULT_WS_BASE, RECONNECT_DELAY_MS, WS_CLIENT_MSG, WS_SERVER_MSG } from "../constants";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { useWebSocket } from "../hooks/useWebSocket";
import { buildWsUrl } from "../lib/api";
import type { ChatMode, LatencySnapshot, TranscriptItem } from "../types";
import { ConversationLog } from "./ConversationLog";

interface VoiceInterfaceProps {
  sessionId: string;
  personaId?: string;
  personaName?: string;
  personaTraits?: string[];
  storyCount?: number;
  hasVoice?: boolean;
  idleVideoUrl?: string | null;
  avatarUrl?: string | null;
  onLatencyUpdate: (latency: LatencySnapshot) => void;
  initialMode?: ChatMode;
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

const MODE_LABELS: Record<ChatMode, string> = {
  text: "Text",
  voice: "Voice",
  video: "Video",
};

export function VoiceInterface({
  sessionId,
  personaId,
  personaName,
  personaTraits = [],
  storyCount = 0,
  hasVoice = false,
  idleVideoUrl,
  avatarUrl,
  onLatencyUpdate,
  initialMode = "voice",
}: VoiceInterfaceProps) {
  const { connect, disconnect, sendJson, sendBinary } = useWebSocket();

  const [items, setItems]               = useState<TranscriptItem[]>([]);
  const [stage, setStage]               = useState<Stage>("idle");
  const [connected, setConnected]       = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isRecording, setIsRecording]   = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [videoUrl, setVideoUrl]             = useState<string | null>(null);
  const [videoLoading, setVideoLoading]     = useState(false);
  const [lastResponseMs, setLastResponseMs] = useState<number | null>(null);
  const [videoGenSeconds, setVideoGenSeconds] = useState<string>("");
  const [playingVideo, setPlayingVideo]       = useState(false);
  const [wsError, setWsError]                 = useState<string | null>(null);
  const [requestedMode, setRequestedMode]   = useState<ChatMode>(initialMode);
  const [negotiatedMode, setNegotiatedMode] = useState<ChatMode>(initialMode);
  // Ref mirrors negotiatedMode so onmessage closure always reads the live value.
  const negotiatedModeRef = useRef<ChatMode>(initialMode);
  const [modeDowngradeNotice, setModeDowngradeNotice] = useState<string | null>(null);
  const [textInput, setTextInput]           = useState<string>("");
  const isRecordingRef   = useRef(false);
  const chunkCountRef    = useRef(0);
  const byteCountRef     = useRef(0);

  useEffect(() => {
    if (!wsError) return;
    const t = setTimeout(() => setWsError(null), 5000);
    return () => clearTimeout(t);
  }, [wsError]);

  useEffect(() => {
    if (!modeDowngradeNotice) return;
    const t = setTimeout(() => setModeDowngradeNotice(null), 6000);
    return () => clearTimeout(t);
  }, [modeDowngradeNotice]);
  const videoGenStartRef = useRef<number>(0);

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
    const ctx = playbackCtxRef.current;
    // AudioContext must have been created in handleMicMouseDown (user gesture).
    // If it's missing here, we're too late for browser autoplay policy.
    if (!ctx) { console.warn("[AUDIO] no AudioContext — was mic button pressed?"); return; }
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
    } catch (e: unknown) {
      const err = e as Error;
      console.error("[AUDIO] decodeAudioData failed:", err?.name, err?.message ?? String(e));
      setWsError("Audio playback failed — try refreshing the page.");
    }
  }

  const doConnect = async (retryCount = 0) => {
    let wsUrl: string;
    try {
      wsUrl = personaId
        ? await buildWsUrl(sessionId, personaId, requestedMode)
        : `${import.meta.env.VITE_WS_BASE_URL ?? DEFAULT_WS_BASE}/ws/${sessionId}`;
    } catch (e) {
      console.error("[WS] failed to build URL:", e);
      setIsConnecting(false);
      return;
    }

    const ws = connect(wsUrl);
    if (!ws) { setIsConnecting(false); return; }

    ws.onopen = () => {
      setConnected(true);
      setIsConnecting(false);
      setIsProcessing(false);
      setIsRecording(false);
    };

    ws.onclose = (e) => {
      setConnected(false);
      setIsConnecting(false);
      setIsProcessing(false);
      setIsRecording(false);
      isRecordingRef.current = false;

      // Persona memories are still processing — surface a message, never retry
      if (e.code === 4010) {
        setWsError("Memories are still building — please try again in a minute.");
        return;
      }

      // Auto-retry once on unexpected close during initial connection
      if (retryCount === 0 && e.code !== 1000) {
        setTimeout(() => {
          setIsConnecting(true);
          doConnect(1);
        }, RECONNECT_DELAY_MS);
      }
    };

    ws.onmessage = async (event) => {
      const message = JSON.parse(event.data);

      if (message.type === WS_SERVER_MSG.TRANSCRIPT) {
        const now = Date.now();
        videoGenStartRef.current    = now;
        turnStartRef.current        = now;
        firstTokenLoggedRef.current = false;
        firstAudioLoggedRef.current = false;
        setStage("LLM");
        if (negotiatedModeRef.current === "video") {
          setVideoLoading(true);
        }
        setItems((current) => [...current, { role: "user", text: message.text }]);
        sentenceChunksRef.current = [];
        nextPlayAtRef.current     = 0;
        playbackLockRef.current   = Promise.resolve();
      }

      if (message.type === WS_SERVER_MSG.VIDEO_READY) {
        const elapsed = ((Date.now() - videoGenStartRef.current) / 1000).toFixed(1);
        setVideoGenSeconds(elapsed);
        setVideoUrl(message.url);
        setVideoLoading(false);
      }

      if (message.type === WS_SERVER_MSG.VIDEO_ERROR) {
        setVideoUrl(null);
        setVideoLoading(false);
      }

      if (message.type === WS_SERVER_MSG.MODE_NEGOTIATED) {
        const negotiated = message.mode as ChatMode;
        const requested  = message.requested as ChatMode;
        negotiatedModeRef.current = negotiated;
        setNegotiatedMode(negotiated);
        if (negotiated !== requested) {
          const label = MODE_LABELS[negotiated];
          const notice = message.reason
            ? `${MODE_LABELS[requested]} not available — using ${label} (${message.reason as string})`
            : `${MODE_LABELS[requested]} not available — using ${label}`;
          setModeDowngradeNotice(notice);
        }
      }

      if (message.type === WS_SERVER_MSG.LLM_TOKEN) {
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

      if (message.type === WS_SERVER_MSG.AUDIO_CHUNK) {
        if (!firstAudioLoggedRef.current) {
          firstAudioLoggedRef.current = true;
        }
        receiveChunk(message.data);
      }

      if (message.type === WS_SERVER_MSG.SENTENCE_END) {
        playbackLockRef.current = playbackLockRef.current.then(() => playSentence());
        await playbackLockRef.current;
      }

      if (message.type === WS_SERVER_MSG.AUDIO_END) {
        playbackLockRef.current = playbackLockRef.current.then(() => playSentence());
        await playbackLockRef.current;
        setIsProcessing(false);
        setIsRecording(false);
        setStage("idle");
        // Safety reset: if not in video mode the spinner must never be stuck.
        if (negotiatedModeRef.current !== "video") {
          setVideoLoading(false);
        }
      }

      if (message.type === WS_SERVER_MSG.ERROR) {
        console.error("[WS] server error:", message.message);
        setWsError(message.message ?? "Something went wrong. Please try again.");
        setIsProcessing(false);
      }

      if (message.type === WS_SERVER_MSG.LATENCY_SUMMARY) {
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

    await new Promise((r) => setTimeout(r, CONNECT_DELAY_MS));
    doConnect(0);
  };

  const handleTextSend = () => {
    const trimmed = textInput.trim();
    if (!trimmed || isProcessing) return;
    setTextInput("");
    setIsProcessing(true);
    setVideoUrl(null);
    setVideoGenSeconds("");
    setPlayingVideo(false);
    sentenceChunksRef.current = [];
    nextPlayAtRef.current     = 0;
    sendJson({ type: WS_CLIENT_MSG.TEXT_TURN, text: trimmed });
  };

  const recorder = useAudioRecorder((pcm) => {
    chunkCountRef.current += 1;
    byteCountRef.current += pcm.byteLength;
    console.debug('[AUDIO_DEBUG] chunk sent to WS: byteLength=' + pcm.byteLength);
    sendBinary(pcm);
  });

  const handleMicMouseDown = async () => {
    if (isRecordingRef.current || isProcessing) return;
    // Create AudioContext synchronously here, inside the user gesture, so browsers
    // allow audio output. Lazy creation in playSentence() is too late — autoplay
    // policy suspends contexts created outside a gesture and resume() is then denied.
    if (!playbackCtxRef.current) {
      playbackCtxRef.current = new AudioContext();
    }
    playbackCtxRef.current.resume().catch(() => {});
    isRecordingRef.current = true;
    setIsRecording(true);
    setStage("recording");
    setVideoUrl(null);
    setVideoGenSeconds("");
    setPlayingVideo(false);
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
    const snapChunks = chunkCountRef.current;
    const snapBytes  = byteCountRef.current;
    chunkCountRef.current = 0;
    byteCountRef.current  = 0;
    recorder.stop(() => {
      console.debug('[AUDIO_DEBUG] audio_end sent — total chunks=' + snapChunks + ' total bytes=' + snapBytes);
      sendJson({ type: WS_CLIENT_MSG.AUDIO_END });
    });
    setStage("STT");
  };

  const micBg = isProcessing ? "#2563EB" : isRecording ? "#16A34A" : "#18181B";

  return (
    <div className="flex flex-col gap-0 overflow-hidden rounded-2xl border border-border bg-surface shadow-card lg:flex-row" style={{ minHeight: '520px' }}>

      {/* ── LEFT PANEL — Avatar + Controls (40%) ── */}
      <div className="flex flex-col items-center gap-5 border-b border-border bg-elevated p-6 lg:w-[40%] lg:border-b-0 lg:border-r">

        {/* WS error banner */}
        {wsError && (
          <div className="flex w-full items-center justify-between rounded-xl bg-red/10 px-4 py-2.5">
            <span className="font-sans text-xs text-red">{wsError}</span>
            <button
              onClick={() => setWsError(null)}
              className="ml-3 font-sans text-xs text-red/60 transition-opacity hover:text-red"
            >
              ✕
            </button>
          </div>
        )}

        {/* Portrait avatar */}
        <div className="relative w-full max-w-[260px] overflow-hidden rounded-2xl shadow-card-hover" style={{ aspectRatio: '3/4' }}>
          {/* D-ID response video — plays in portrait when replay is clicked */}
          {playingVideo && videoUrl && (
            <video
              src={videoUrl}
              autoPlay
              playsInline
              className="h-full w-full object-cover"
              onEnded={() => { setPlayingVideo(false); }}
            />
          )}

          {/* Tavus idle video — loops silently when not playing a D-ID response */}
          {!playingVideo && idleVideoUrl && (
            <video
              src={idleVideoUrl}
              autoPlay
              loop
              muted
              playsInline
              className="h-full w-full object-cover"
            />
          )}

          {/* Static avatar photo — fallback when no idle video */}
          {!playingVideo && !idleVideoUrl && avatarUrl && (
            <img
              src={avatarUrl}
              alt={personaName ?? "Persona"}
              className="h-full w-full object-cover"
              style={{ filter: 'blur(0px)' }}
            />
          )}

          {/* Letter / spinner placeholder */}
          {!playingVideo && !idleVideoUrl && !avatarUrl && (
            <div className="flex h-full w-full items-center justify-center" style={{ backgroundColor: '#FAFAF9' }}>
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

          {/* Capability chips */}
          <div className="flex flex-wrap justify-center gap-2">
            <span className={`rounded-full px-2.5 py-0.5 font-sans text-[10px] ${hasVoice ? 'bg-green/10 text-green' : 'bg-cream text-muted'}`}>
              {hasVoice ? 'Voice: Cloned' : 'Voice: Not configured'}
            </span>
            <span className={`rounded-full px-2.5 py-0.5 font-sans text-[10px] ${(avatarUrl || idleVideoUrl) ? 'bg-green/10 text-green' : 'bg-cream text-muted'}`}>
              {idleVideoUrl ? 'Avatar: Video' : avatarUrl ? 'Avatar: Photo' : 'Avatar: Letter'}
            </span>
          </div>

          {!connected ? (
            <>
              {/* Mode picker — shown only before connecting */}
              <div className="flex w-full items-center justify-center gap-1.5">
                {(["text", "voice", "video"] as ChatMode[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => setRequestedMode(m)}
                    className={`flex-1 rounded-lg border py-1.5 font-sans text-[11px] font-medium transition-colors ${
                      requestedMode === m
                        ? "border-accent bg-accent/10 text-accent"
                        : "border-border bg-surface text-muted hover:border-border-hi hover:text-text"
                    }`}
                  >
                    {MODE_LABELS[m]}
                  </button>
                ))}
              </div>

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
            </>
          ) : (
            <>
              {/* Mode badge — shown after connecting, locked to negotiated mode */}
              <div className="flex items-center gap-1.5">
                <span className="rounded-full bg-cream px-2.5 py-0.5 font-sans text-[10px] text-muted">
                  Mode:
                </span>
                <span className="rounded-full bg-accent/10 px-2.5 py-0.5 font-sans text-[10px] font-medium text-accent capitalize">
                  {negotiatedMode}
                </span>
              </div>

              {/* Mode downgrade notice */}
              {modeDowngradeNotice && (
                <div className="flex w-full items-center justify-between rounded-xl bg-amber/10 px-3 py-2">
                  <span className="font-sans text-[10px] text-amber-700">{modeDowngradeNotice}</span>
                  <button
                    onClick={() => setModeDowngradeNotice(null)}
                    className="ml-2 font-sans text-[10px] text-amber-700/60 hover:text-amber-700"
                  >
                    ✕
                  </button>
                </div>
              )}

              {/* Voice / Video mode: mic button */}
              {(negotiatedMode === "voice" || negotiatedMode === "video") && (
                <>
                  <p className="font-sans text-[11px] text-muted">
                    {isProcessing ? "Processing…" : isRecording ? "Listening…" : "Hold to speak"}
                  </p>

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

                  {isRecording && (
                    <div className="flex items-center gap-0.5">
                      {Array.from({ length: 14 }).map((_, i) => (
                        <span key={i} className="wave-bar" style={{ animationDelay: `${i * 45}ms` }} />
                      ))}
                    </div>
                  )}
                </>
              )}

              {/* Text mode: text input */}
              {negotiatedMode === "text" && (
                <div className="flex w-full gap-2">
                  <input
                    type="text"
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleTextSend(); }}
                    disabled={isProcessing}
                    placeholder={isProcessing ? "Processing…" : "Type a message…"}
                    className="flex-1 rounded-xl border border-border bg-surface px-3 py-2 font-sans text-xs text-text placeholder:text-muted focus:border-accent focus:outline-none disabled:opacity-50"
                  />
                  <button
                    onClick={handleTextSend}
                    disabled={isProcessing || !textInput.trim()}
                    className="rounded-xl bg-accent px-3 py-2 font-sans text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Send
                  </button>
                </div>
              )}

              {/* Pipeline status */}
              <PipelineBar stage={stage} />

              {/* End session */}
              <button
                className="font-sans text-[11px] text-muted transition-colors hover:text-red"
                onClick={disconnect}
              >
                End session
              </button>
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
          hasVoice={hasVoice}
          storyCount={storyCount}
        />

        {/* Video mode panel — live video stream or generating spinner */}
        {negotiatedMode === "video" && connected && (
          <div className="border-t border-border px-4 py-3">
            {videoUrl ? (
              <video
                src={videoUrl}
                autoPlay
                playsInline
                controls
                className="w-full rounded-xl"
                onEnded={() => setVideoUrl(null)}
              />
            ) : videoLoading ? (
              <div className="flex items-center gap-2 py-2">
                <svg className="h-4 w-4 animate-spin text-accent" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span className="font-mono text-[11px] text-muted">Generating video…</span>
              </div>
            ) : null}
          </div>
        )}

        {/* Watch replay button — voice mode only (video mode renders inline above) */}
        {negotiatedMode !== "video" && videoUrl && !playingVideo && (
          <div className="border-t border-border px-4 py-3">
            <button
              onClick={() => setPlayingVideo(true)}
              className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 font-mono text-[11px] text-textdim transition-colors hover:border-border-hi hover:text-text"
            >
              <span>▶</span>
              <span>Avatar response ready · {videoGenSeconds}s to generate</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
