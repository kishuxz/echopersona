import { Camera, Mic, Plus, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPersona, uploadAvatar, uploadVoice } from "../lib/api";
import type { Persona } from "../types";

interface PersonaUploadProps {
  onPersona: (persona: Persona) => void;
  activePersona?: Persona | null;
}

export function PersonaUpload({ onPersona, activePersona }: PersonaUploadProps) {
  const [name, setName] = useState("Demo Persona");
  const [stories, setStories] = useState(["They love explaining technical systems clearly and briefly."]);
  const [traits, setTraits] = useState("warm, direct, technical");
  const [style, setStyle] = useState("short sentences, calm pacing");
  const [voiceFiles, setVoiceFiles] = useState<File[]>([]);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<"idle" | "cloning" | "cloned" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(true);

  // Voice recording
  const [voiceTab, setVoiceTab] = useState<"upload" | "record">("upload");
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [finalDuration, setFinalDuration] = useState(0);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [recordedUrl, setRecordedUrl] = useState<string | null>(null);
  const [micError, setMicError] = useState<string | null>(null);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);

  // Camera capture
  const [avatarTab, setAvatarTab] = useState<"upload" | "camera">("upload");
  const [cameraMode, setCameraMode] = useState(false);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Recording duration timer — resets when recording stops
  useEffect(() => {
    if (!isRecording) { setRecordingDuration(0); return; }
    const interval = setInterval(() => setRecordingDuration(d => d + 1), 1000);
    return () => clearInterval(interval);
  }, [isRecording]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach(t => t.stop());
    };
  }, []);

  const formatDuration = (s: number) =>
    `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  // ── Audio recording ──────────────────────────────────────────────────────────

  const startRecording = async () => {
    setMicError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicError("Recording requires HTTPS. Please upload a file instead.");
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      setMicError("Your browser doesn't support recording. Please upload a file instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      audioChunks.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(audioChunks.current, { type: "audio/webm" });
        setRecordedBlob(blob);
        setRecordedUrl(URL.createObjectURL(blob));
        stream.getTracks().forEach(t => t.stop());
      };

      recorder.start(250);
      mediaRecorder.current = recorder;
      setIsRecording(true);
    } catch {
      setMicError("Microphone access denied. Please upload a file instead.");
    }
  };

  const stopRecording = () => {
    setFinalDuration(recordingDuration);
    mediaRecorder.current?.stop();
    setIsRecording(false);
  };

  const useRecording = () => {
    if (!recordedBlob) return;
    const file = new File(
      [recordedBlob],
      `voice-recording-${Date.now()}.webm`,
      { type: "audio/webm" }
    );
    setVoiceFiles(prev => [...prev, file]);
    if (recordedUrl) URL.revokeObjectURL(recordedUrl);
    setRecordedBlob(null);
    setRecordedUrl(null);
    setVoiceStatus("idle");
  };

  const reRecord = () => {
    if (recordedUrl) URL.revokeObjectURL(recordedUrl);
    setRecordedBlob(null);
    setRecordedUrl(null);
  };

  // ── Camera capture ───────────────────────────────────────────────────────────

  const startCamera = async () => {
    setCameraError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Camera requires HTTPS. Please upload a photo instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: 640, height: 640 },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
      setCameraMode(true);
    } catch {
      setCameraError("Camera access denied. Please upload a photo instead.");
    }
  };

  const capturePhoto = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const canvas = canvasRef.current;
    canvas.width = 640;
    canvas.height = 640;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(videoRef.current, 0, 0, 640, 640);
    setCapturedImage(canvas.toDataURL("image/jpeg", 0.9));
    streamRef.current?.getTracks().forEach(t => t.stop());
    setCameraMode(false);
  };

  const usePhoto = () => {
    if (!capturedImage || !canvasRef.current) return;
    canvasRef.current.toBlob((blob) => {
      if (!blob) return;
      const file = new File([blob], `avatar-${Date.now()}.jpg`, { type: "image/jpeg" });
      setAvatarFile(file);
      setAvatarPreview(capturedImage);
    }, "image/jpeg", 0.9);
    setCapturedImage(null);
  };

  const retakePhoto = () => {
    setCapturedImage(null);
    startCamera();
  };

  const cancelCamera = () => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    setCameraMode(false);
  };

  // ── Submit ───────────────────────────────────────────────────────────────────

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      let persona = await createPersona({
        name,
        stories,
        personality_traits: traits.split(",").map((t) => t.trim()).filter(Boolean),
        speaking_style: style,
      });

      if (voiceFiles.length) {
        setVoiceStatus("cloning");
        try {
          persona = await uploadVoice(persona.id, voiceFiles);
          setVoiceStatus("cloned");
        } catch (e) {
          console.error("[VOICE CLONE]", e);
          setVoiceStatus("error");
        }
      }

      if (avatarFile) {
        try {
          persona = await uploadAvatar(persona.id, avatarFile);
        } catch (e) {
          console.error("[AVATAR UPLOAD]", e);
        }
      }

      onPersona(persona);
      setShowForm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create persona");
    } finally {
      setBusy(false);
    }
  };

  // ── Styles ───────────────────────────────────────────────────────────────────

  const inputCls =
    "w-full rounded border border-border bg-bg px-3 py-2 font-sans text-sm text-text placeholder:text-muted outline-none transition-colors focus:border-green";
  const labelCls = "block font-mono text-[10px] uppercase tracking-widest text-textdim mb-1";

  const tabCls = (active: boolean) =>
    `flex flex-1 items-center justify-center gap-1.5 rounded py-1.5 font-mono text-[10px] transition-colors ${
      active
        ? "bg-surface border border-green text-green"
        : "text-textdim hover:text-text"
    }`;

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="rounded-lg border border-border bg-surface">
      {/* Always-present hidden canvas for photo capture */}
      <canvas ref={canvasRef} className="hidden" />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="font-mono text-[10px] uppercase tracking-widest text-textdim">
          Persona
        </span>
        {activePersona && (
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-green">{activePersona.name}</span>
            <button
              className="font-mono text-[10px] text-muted transition-colors hover:text-red"
              onClick={() => { setShowForm(true); setVoiceStatus("idle"); }}
              title="Change persona"
            >
              change
            </button>
          </div>
        )}
      </div>

      {/* Active persona summary */}
      {activePersona && !showForm && (
        <div className="p-4">
          <div className="rounded border border-green/20 bg-bg p-3">
            <p className="font-mono text-sm font-bold text-green">{activePersona.name}</p>
            <p className="mt-1 font-sans text-xs text-textdim">{activePersona.speaking_style}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {activePersona.personality_traits.map((t) => (
                <span key={t} className="rounded border border-border px-2 py-0.5 font-mono text-[10px] text-textdim">
                  {t}
                </span>
              ))}
            </div>
          </div>
          <p className="mt-3 font-sans text-xs text-textdim">
            Connect in the voice panel to start talking →
          </p>
        </div>
      )}

      {showForm && (
        <div className="flex flex-col gap-3 p-4">
          {/* Name */}
          <div>
            <label className={labelCls}>Name</label>
            <input
              className={inputCls}
              placeholder="e.g. David Letterman"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* Personality traits */}
          <div>
            <label className={labelCls}>Personality traits</label>
            <textarea
              className={inputCls + " min-h-[60px] resize-y"}
              placeholder="e.g. sarcastic, witty, loves comedy"
              value={traits}
              onChange={(e) => setTraits(e.target.value)}
            />
          </div>

          {/* Speaking style */}
          <div>
            <label className={labelCls}>Speaking style</label>
            <textarea
              className={inputCls + " min-h-[60px] resize-y"}
              placeholder="e.g. dry humor, long pauses"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
            />
          </div>

          {/* Memory stories */}
          <div>
            <label className={labelCls}>Memory stories</label>
            <div className="flex flex-col gap-2">
              {stories.map((story, i) => (
                <div key={i} className="relative">
                  <textarea
                    className={inputCls + " min-h-[72px] resize-y pr-8 font-mono text-xs"}
                    placeholder={`Story ${i + 1}…`}
                    value={story}
                    onChange={(e) =>
                      setStories((cur) => cur.map((item, j) => (j === i ? e.target.value : item)))
                    }
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-2 text-muted transition-colors hover:text-red"
                    onClick={() => setStories((cur) => cur.filter((_, j) => j !== i))}
                    title="Remove story"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="mt-2 flex w-full items-center justify-center gap-1.5 rounded border border-border py-2 font-mono text-xs text-textdim transition-colors hover:border-green hover:text-green"
              onClick={() => setStories((cur) => [...cur, ""])}
            >
              <Plus size={13} /> Add story
            </button>
          </div>

          {/* ── Voice samples ─────────────────────────────────────────────── */}
          <div>
            <label className={labelCls}>Voice samples (optional)</label>

            {/* Tab switcher */}
            <div className="mb-2 flex gap-1 rounded border border-border p-0.5">
              <button type="button" onClick={() => { setVoiceTab("record"); setMicError(null); }} className={tabCls(voiceTab === "record")}>
                <Mic size={11} /> Record Voice
              </button>
              <button type="button" onClick={() => setVoiceTab("upload")} className={tabCls(voiceTab === "upload")}>
                <Upload size={11} /> Upload File
              </button>
            </div>

            {/* Record tab */}
            {voiceTab === "record" && (
              <div className="rounded border border-border bg-bg p-3">
                {micError && (
                  <p className="mb-2 font-mono text-[10px] text-red">{micError}</p>
                )}

                {/* Idle: start button */}
                {!isRecording && !recordedBlob && (
                  <button
                    type="button"
                    onClick={startRecording}
                    className="flex w-full items-center justify-center gap-2 rounded border border-border py-3 font-mono text-xs text-textdim transition-colors hover:border-green hover:text-green"
                  >
                    <Mic size={14} /> Start Recording
                  </button>
                )}

                {/* Recording in progress */}
                {isRecording && (
                  <div className="flex flex-col items-center gap-3 py-2">
                    <div className="relative flex items-center justify-center">
                      <div className="absolute h-8 w-8 animate-ping rounded-full bg-red/30" />
                      <div className="h-5 w-5 rounded-full bg-red" />
                    </div>
                    <span className="font-mono text-sm text-green">{formatDuration(recordingDuration)}</span>
                    <div className="flex items-center gap-0.5">
                      {Array.from({ length: 18 }).map((_, i) => (
                        <span key={i} className="wave-bar" style={{ animationDelay: `${i * 45}ms` }} />
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={stopRecording}
                      className="rounded border border-red/30 px-4 py-1.5 font-mono text-xs text-red transition-colors hover:border-red"
                    >
                      Stop Recording
                    </button>
                  </div>
                )}

                {/* Recorded clip review */}
                {recordedBlob && recordedUrl && (
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-textdim">
                        Recorded: {formatDuration(finalDuration)}
                      </span>
                    </div>
                    {finalDuration < 10 && (
                      <p className="font-mono text-[10px] text-yellow">
                        Recording too short — ElevenLabs needs 30+ seconds for best results
                      </p>
                    )}
                    <audio src={recordedUrl} controls className="h-8 w-full" />
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={useRecording}
                        className="flex-1 rounded bg-green py-2 font-mono text-xs font-bold text-black transition-opacity hover:opacity-90"
                      >
                        Use This Recording
                      </button>
                      <button
                        type="button"
                        onClick={reRecord}
                        className="font-mono text-[10px] text-textdim transition-colors hover:text-text"
                      >
                        Re-record
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Upload tab */}
            {voiceTab === "upload" && (
              <label className="flex cursor-pointer flex-col items-center gap-2 rounded border-2 border-dashed border-border py-4 transition-colors hover:border-green hover:bg-green/[0.03]">
                <Upload size={18} className="text-textdim" />
                <span className="font-mono text-[10px] text-textdim">Drop audio files here</span>
                <input
                  type="file"
                  accept="audio/*"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files) {
                      setVoiceFiles(prev => [...prev, ...Array.from(e.target.files!)]);
                      setVoiceStatus("idle");
                    }
                  }}
                />
              </label>
            )}

            {/* Voice files list */}
            {voiceFiles.length > 0 && (
              <div className="mt-2 flex flex-col gap-1">
                {voiceFiles.map((f, i) => (
                  <div key={i} className="flex items-center justify-between rounded border border-border bg-bg px-2 py-1">
                    <span className="font-mono text-[10px] text-textdim">
                      {f.name.startsWith("voice-recording") ? "🎤" : "📁"} {f.name}
                    </span>
                    <button
                      type="button"
                      onClick={() => setVoiceFiles(prev => prev.filter((_, j) => j !== i))}
                      className="text-muted transition-colors hover:text-red"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Voice clone status */}
            {voiceStatus === "cloning" && (
              <div className="mt-2 flex items-center gap-2">
                <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="#00ff88" strokeWidth="3" />
                  <path className="opacity-80" fill="#00ff88" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span className="font-mono text-[10px] text-textdim">Cloning voice…</span>
              </div>
            )}
            {voiceStatus === "cloned" && (
              <p className="mt-2 font-mono text-[10px] text-green">✓ Voice cloned</p>
            )}
            {voiceStatus === "error" && (
              <p className="mt-2 font-mono text-[10px] text-red">Voice clone failed — using default voice</p>
            )}
          </div>

          {/* ── Avatar image ──────────────────────────────────────────────── */}
          <div>
            <label className={labelCls}>Face photo for video avatar (optional)</label>

            {/* Tab switcher */}
            <div className="mb-2 flex gap-1 rounded border border-border p-0.5">
              <button type="button" onClick={() => { setAvatarTab("camera"); setCameraError(null); }} className={tabCls(avatarTab === "camera")}>
                <Camera size={11} /> Take Photo
              </button>
              <button type="button" onClick={() => setAvatarTab("upload")} className={tabCls(avatarTab === "upload")}>
                <Upload size={11} /> Upload Photo
              </button>
            </div>

            {/* Camera tab */}
            {avatarTab === "camera" && (
              <div className="rounded border border-border bg-bg p-3">
                {cameraError && (
                  <p className="mb-2 font-mono text-[10px] text-red">{cameraError}</p>
                )}

                {/* Idle: no capture yet */}
                {!capturedImage && (
                  <button
                    type="button"
                    onClick={startCamera}
                    className="flex w-full items-center justify-center gap-2 rounded border border-border py-3 font-mono text-xs text-textdim transition-colors hover:border-green hover:text-green"
                  >
                    <Camera size={14} /> Open Camera
                  </button>
                )}

                {/* Captured image review */}
                {capturedImage && (
                  <div className="flex flex-col items-center gap-3">
                    <img
                      src={capturedImage}
                      alt="Captured"
                      className="h-32 w-32 rounded-full border-2 border-green object-cover"
                    />
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={usePhoto}
                        className="rounded bg-green px-4 py-2 font-mono text-xs font-bold text-black transition-opacity hover:opacity-90"
                      >
                        Use This Photo
                      </button>
                      <button
                        type="button"
                        onClick={retakePhoto}
                        className="font-mono text-[10px] text-textdim transition-colors hover:text-text"
                      >
                        Retake
                      </button>
                    </div>
                  </div>
                )}

                {/* Show confirmed avatar */}
                {!capturedImage && avatarFile && avatarPreview && (
                  <div className="mt-2 flex items-center gap-2">
                    <img src={avatarPreview} alt="Avatar" className="h-8 w-8 rounded-full object-cover" />
                    <span className="font-mono text-[10px] text-green">✓ {avatarFile.name}</span>
                  </div>
                )}
              </div>
            )}

            {/* Upload tab */}
            {avatarTab === "upload" && (
              <>
                <label className="flex cursor-pointer flex-col items-center gap-2 rounded border-2 border-dashed border-border py-4 transition-colors hover:border-green hover:bg-green/[0.03]">
                  {avatarPreview ? (
                    <img
                      src={avatarPreview}
                      alt="Avatar preview"
                      className="h-20 w-20 rounded-full object-cover"
                    />
                  ) : (
                    <>
                      <Upload size={18} className="text-textdim" />
                      <span className="font-mono text-[10px] text-textdim">Upload face photo (JPG/PNG)</span>
                    </>
                  )}
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0] ?? null;
                      setAvatarFile(f);
                      if (f) setAvatarPreview(URL.createObjectURL(f));
                      else setAvatarPreview(null);
                    }}
                  />
                </label>
                {avatarFile && (
                  <p className="mt-1 font-mono text-[10px] text-textdim">{avatarFile.name}</p>
                )}
              </>
            )}
          </div>

          {error && <p className="font-mono text-[10px] text-red">{error}</p>}

          <button
            className="mt-1 w-full rounded py-3 font-mono text-sm font-bold uppercase tracking-widest transition-all disabled:opacity-40"
            style={
              busy
                ? { background: "#111", border: "1px solid #00ff88", color: "#00ff88" }
                : { background: "#00ff88", color: "#00170c" }
            }
            onClick={submit}
            disabled={busy}
          >
            {busy ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="#00ff88" strokeWidth="3" />
                  <path className="opacity-80" fill="#00ff88" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Building persona…
              </span>
            ) : (
              "Build Persona"
            )}
          </button>
        </div>
      )}

      {/* Camera modal overlay */}
      {cameraMode && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/80">
          <div className="flex flex-col items-center gap-4">
            <p className="font-mono text-[10px] uppercase tracking-widest text-textdim">
              Position your face in the circle
            </p>
            <video
              ref={videoRef}
              className="h-64 w-64 rounded-full border-2 border-green object-cover"
              autoPlay
              playsInline
              muted
            />
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={capturePhoto}
                className="rounded bg-green px-6 py-2.5 font-mono text-sm font-bold text-black transition-opacity hover:opacity-90"
              >
                Capture
              </button>
              <button
                type="button"
                onClick={cancelCamera}
                className="font-mono text-xs text-textdim transition-colors hover:text-text"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
