import { Camera, Mic, Plus, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPersona, saveSimliFaceId, updatePersona, uploadAvatar, uploadVoice } from "../lib/api";
import type { Persona } from "../types";

interface PersonaUploadProps {
  onPersona: (persona: Persona) => void;
  activePersona?: Persona | null;
  existingPersona?: Persona;
}

type FormStep = "profile" | "voice" | "photo" | "done";

const STEPS: { key: FormStep; label: string }[] = [
  { key: "profile", label: "Profile" },
  { key: "voice",   label: "Voice"   },
  { key: "photo",   label: "Photo"   },
  { key: "done",    label: "Done"    },
];

function StepIndicator({ current }: { current: FormStep }) {
  const currentIdx = STEPS.findIndex((s) => s.key === current);
  return (
    <div className="flex items-center gap-0 mb-6">
      {STEPS.map((s, i) => {
        const done    = i < currentIdx;
        const active  = i === currentIdx;
        return (
          <div key={s.key} className="flex flex-1 flex-col items-center gap-1">
            <div className="flex w-full items-center">
              {i > 0 && <div className={`flex-1 h-px ${done ? "bg-green" : "bg-border"}`} />}
              <div
                className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border-2 text-[10px] font-medium transition-all duration-200 ${
                  done
                    ? "border-green bg-green text-white"
                    : active
                    ? "border-accent bg-accent text-white"
                    : "border-border bg-surface text-muted"
                }`}
              >
                {done ? "✓" : i + 1}
              </div>
              {i < STEPS.length - 1 && <div className={`flex-1 h-px ${done ? "bg-green" : "bg-border"}`} />}
            </div>
            <span className={`font-sans text-[9px] uppercase tracking-widest ${active ? "text-text" : "text-muted"}`}>
              {s.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function PersonaUpload({ onPersona, activePersona, existingPersona }: PersonaUploadProps) {
  const [name, setName] = useState("");
  const [stories, setStories] = useState([""]);
  const [traits, setTraits] = useState("");
  const [style, setStyle] = useState("");
  const [voiceFiles, setVoiceFiles] = useState<File[]>([]);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const avatarFileRef = useRef<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [simliId, setSimliId] = useState("");
  const [busy, setBusy] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<"idle" | "cloning" | "cloned" | "error">("idle");
  const [avatarError, setAvatarError] = useState<string | null>(null);
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

  // Derive current step for the indicator
  const currentStep: FormStep = (() => {
    if (!showForm) return "done";
    if (voiceFiles.length > 0 || voiceStatus === "cloned") return "photo";
    if (name.trim().length > 2 && stories.some(s => s.trim().length > 0)) return "voice";
    return "profile";
  })();

  const updateAvatarFile = (file: File | null) => {
    avatarFileRef.current = file;
    setAvatarFile(file);
  };

  // Pre-fill form fields when editing an existing persona
  useEffect(() => {
    if (!existingPersona) return;
    setName(existingPersona.name);
    setStories(existingPersona.stories.length ? existingPersona.stories : [""]);
    setTraits(existingPersona.personality_traits.join(", "));
    setStyle(existingPersona.speaking_style);
  }, [existingPersona?.id]);

  useEffect(() => {
    if (!isRecording) { setRecordingDuration(0); return; }
    const interval = setInterval(() => setRecordingDuration(d => d + 1), 1000);
    return () => clearInterval(interval);
  }, [isRecording]);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach(t => t.stop());
    };
  }, []);

  // Attach camera stream after cameraMode=true renders the video element
  useEffect(() => {
    if (cameraMode && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
      videoRef.current.play().catch(() => {});
    }
  }, [cameraMode]);

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
      setCameraMode(true);
      // Stream is attached to the video element via useEffect once cameraMode=true renders it
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
    const snapshotUrl = capturedImage;
    canvasRef.current.toBlob((blob) => {
      if (!blob) return;
      const file = new File([blob], `avatar-${Date.now()}.jpg`, { type: "image/jpeg" });
      updateAvatarFile(file);
      setAvatarPreview(snapshotUrl);
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
    if (name.trim().length < 2) {
      setError("Please enter a name (at least 2 characters).");
      return;
    }
    if (!stories.some((s) => s.trim().length > 0)) {
      setError("Please add at least one memory story.");
      return;
    }
    setBusy(true);
    setError(null);
    setAvatarError(null);
    try {
      const formData = {
        name,
        stories,
        personality_traits: traits.split(",").map((t) => t.trim()).filter(Boolean),
        speaking_style: style,
      };
      let persona = existingPersona
        ? await updatePersona(existingPersona.id, formData)
        : await createPersona(formData);

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

      const fileToUpload = avatarFileRef.current ?? avatarFile;
      if (fileToUpload) {
        try {
          persona = await uploadAvatar(persona.id, fileToUpload);
        } catch (e) {
          console.error("[AVATAR UPLOAD]", e);
          setAvatarError("Photo upload failed — persona created without avatar.");
        }
      }

      if (simliId.trim()) {
        try {
          persona = await saveSimliFaceId(persona.id, simliId.trim());
        } catch (e) {
          console.error("[SIMLI FACE]", e);
        }
      }

      onPersona(persona);
      setShowForm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : existingPersona ? "Failed to update persona" : "Failed to create persona");
    } finally {
      setBusy(false);
    }
  };

  // ── Styles ───────────────────────────────────────────────────────────────────

  const inputCls =
    "w-full rounded-none border-0 border-b border-border bg-transparent px-0 py-2.5 font-sans text-sm text-text placeholder:text-muted outline-none transition-colors focus:border-blue";

  const labelCls = "block font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-muted mb-1.5";

  const tabCls = (active: boolean) =>
    `flex flex-1 items-center justify-center gap-1.5 rounded-lg py-1.5 font-sans text-[11px] font-medium transition-all duration-150 ${
      active
        ? "bg-accent text-white"
        : "text-muted hover:text-textdim"
    }`;

  const sectionNum = (n: string) => (
    <div className="mb-2.5 flex items-center gap-2.5">
      <span className="font-mono text-[9px] text-muted">{n}</span>
      <div className="h-px flex-1 bg-border" />
    </div>
  );

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="rounded-xl border border-border bg-surface shadow-card">
      {/* Always-present hidden canvas for photo capture */}
      <canvas ref={canvasRef} className="hidden" />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-muted">
          {existingPersona ? "Edit Persona" : "New Persona"}
        </span>
        {activePersona && (
          <div className="flex items-center gap-2">
            <span className="font-sans text-sm font-semibold text-text">{activePersona.name}</span>
            <button
              className="font-sans text-[11px] text-muted transition-colors hover:text-red"
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
          <div className="rounded-lg border border-border bg-elevated p-3">
            <p className="font-sans text-sm font-semibold text-text">{activePersona.name}</p>
            <p className="mt-1 font-sans text-xs text-textdim">{activePersona.speaking_style}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {activePersona.personality_traits.map((t) => (
                <span key={t} className="rounded-full bg-cream px-2.5 py-0.5 font-sans text-[11px] text-textdim">
                  {t}
                </span>
              ))}
            </div>
          </div>
          <p className="mt-3 font-sans text-xs text-muted">
            Connect in the voice panel to start talking →
          </p>
        </div>
      )}

      {showForm && (
        <div className="flex flex-col gap-4 p-4">

          {/* Step indicator */}
          <StepIndicator current={currentStep} />

          {/* 01 Name */}
          <div>
            {sectionNum("01")}
            <label className={labelCls}>Name</label>
            <input
              className={inputCls}
              placeholder="e.g. David Letterman"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* 02 Personality traits */}
          <div>
            {sectionNum("02")}
            <label className={labelCls}>Personality traits</label>
            <textarea
              className={inputCls + " min-h-[56px] resize-y"}
              placeholder="e.g. sarcastic, witty, loves comedy"
              value={traits}
              onChange={(e) => setTraits(e.target.value)}
            />
          </div>

          {/* 03 Speaking style */}
          <div>
            {sectionNum("03")}
            <label className={labelCls}>Speaking style</label>
            <textarea
              className={inputCls + " min-h-[56px] resize-y"}
              placeholder="e.g. dry humor, long pauses"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
            />
          </div>

          {/* 04 Memory stories */}
          <div>
            {sectionNum("04")}
            <label className={labelCls}>Memory stories</label>
            <p className="mb-2 font-sans text-[10px] text-muted">
              Required — the more memories you share, the more alive they feel
            </p>
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
                    className="absolute right-0 top-2 text-muted transition-colors hover:text-red"
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
              className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg border border-border py-2 font-sans text-xs text-muted transition-colors hover:border-accent hover:text-textdim"
              onClick={() => setStories((cur) => [...cur, ""])}
            >
              <Plus size={13} /> Add story
            </button>
          </div>

          {/* 05 Voice samples */}
          <div>
            {sectionNum("05")}
            <label className={labelCls}>Voice samples (optional)</label>
            <p className="mb-2 font-sans text-[10px] text-muted">
              Quiet room, natural speech — 30 seconds is enough to capture a voice forever
            </p>

            {/* Tab switcher */}
            <div className="mb-2 flex gap-1 rounded-lg border border-border p-0.5">
              <button type="button" onClick={() => { setVoiceTab("record"); setMicError(null); }} className={tabCls(voiceTab === "record")}>
                <Mic size={11} /> Record Voice
              </button>
              <button type="button" onClick={() => setVoiceTab("upload")} className={tabCls(voiceTab === "upload")}>
                <Upload size={11} /> Upload File
              </button>
            </div>

            {/* Record tab */}
            {voiceTab === "record" && (
              <div className="rounded-lg border border-border bg-elevated p-3">
                {micError && (
                  <p className="mb-2 font-sans text-[11px] text-red">{micError}</p>
                )}

                {!isRecording && !recordedBlob && (
                  <button
                    type="button"
                    onClick={startRecording}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-border py-3 font-sans text-sm text-muted transition-colors hover:border-accent hover:text-textdim"
                  >
                    <Mic size={14} /> Start Recording
                  </button>
                )}

                {isRecording && (
                  <div className="flex flex-col items-center gap-3 py-2">
                    <div className="relative flex items-center justify-center">
                      <div className="absolute h-8 w-8 animate-ping rounded-full bg-red/20" />
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
                      className="rounded-lg border border-red/30 px-4 py-1.5 font-sans text-sm text-red transition-colors hover:border-red/60"
                    >
                      Stop Recording
                    </button>
                  </div>
                )}

                {recordedBlob && recordedUrl && (
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-muted">
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
                        className="flex-1 rounded-lg bg-accent py-2 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
                      >
                        Use This Recording
                      </button>
                      <button
                        type="button"
                        onClick={reRecord}
                        className="font-sans text-[11px] text-muted transition-colors hover:text-textdim"
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
              <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border py-5 transition-colors hover:border-border-hi hover:bg-elevated">
                <Upload size={18} className="text-muted" />
                <span className="font-sans text-[11px] text-muted">Drop audio files here</span>
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
                  <div key={i} className="flex items-center justify-between rounded-lg border border-border bg-elevated px-3 py-1.5">
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
                <svg className="h-3 w-3 animate-spin text-green" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span className="font-sans text-[11px] text-textdim">Cloning voice…</span>
              </div>
            )}
            {voiceStatus === "cloned" && (
              <p className="mt-2 font-sans text-[11px] text-green">✓ Voice cloned</p>
            )}
            {voiceStatus === "error" && (
              <p className="mt-2 font-sans text-[11px] text-red">Voice clone failed — using default voice</p>
            )}
          </div>

          {/* 06 Avatar image */}
          <div>
            {sectionNum("06")}
            <label className={labelCls}>Face photo for video avatar (optional)</label>

            {/* Tab switcher */}
            <div className="mb-2 flex gap-1 rounded-lg border border-border p-0.5">
              <button type="button" onClick={() => { setAvatarTab("camera"); setCameraError(null); }} className={tabCls(avatarTab === "camera")}>
                <Camera size={11} /> Take Photo
              </button>
              <button type="button" onClick={() => setAvatarTab("upload")} className={tabCls(avatarTab === "upload")}>
                <Upload size={11} /> Upload Photo
              </button>
            </div>

            {/* Camera tab */}
            {avatarTab === "camera" && (
              <div className="rounded-lg border border-border bg-elevated p-3">
                {cameraError && (
                  <p className="mb-2 font-sans text-[11px] text-red">{cameraError}</p>
                )}

                {!capturedImage && (
                  <button
                    type="button"
                    onClick={startCamera}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-border py-3 font-sans text-sm text-muted transition-colors hover:border-accent hover:text-textdim"
                  >
                    <Camera size={14} /> Open Camera
                  </button>
                )}

                {capturedImage && (
                  <div className="flex flex-col items-center gap-3">
                    <img
                      src={capturedImage}
                      alt="Captured"
                      className="h-28 w-28 rounded-full border-2 border-green/50 object-cover"
                    />
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={usePhoto}
                        className="rounded-lg bg-accent px-4 py-2 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
                      >
                        Use This Photo
                      </button>
                      <button
                        type="button"
                        onClick={retakePhoto}
                        className="font-sans text-[11px] text-muted transition-colors hover:text-textdim"
                      >
                        Retake
                      </button>
                    </div>
                  </div>
                )}

                {!capturedImage && avatarFile && avatarPreview && (
                  <div className="mt-2 flex items-center gap-2">
                    <img src={avatarPreview} alt="Avatar" className="h-8 w-8 rounded-full object-cover" />
                    <span className="font-sans text-[11px] text-green">✓ {avatarFile.name}</span>
                  </div>
                )}
              </div>
            )}

            {/* Upload tab */}
            {avatarTab === "upload" && (
              <>
                <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border py-5 transition-colors hover:border-border-hi hover:bg-elevated">
                  {avatarPreview ? (
                    <img
                      src={avatarPreview}
                      alt="Avatar preview"
                      className="h-24 w-24 rounded-full border-2 border-green/30 object-cover shadow-card"
                    />
                  ) : (
                    <>
                      <Upload size={18} className="text-muted" />
                      <span className="font-sans text-[11px] text-muted">Upload face photo (JPG/PNG)</span>
                    </>
                  )}
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0] ?? null;
                      updateAvatarFile(f);
                      if (f) setAvatarPreview(URL.createObjectURL(f));
                      else setAvatarPreview(null);
                    }}
                  />
                </label>
                {avatarFile && (
                  <p className="mt-1 font-mono text-[10px] text-muted">{avatarFile.name}</p>
                )}
              </>
            )}
            {avatarError && (
              <p className="mt-1.5 font-sans text-[11px] text-red">{avatarError}</p>
            )}
          </div>

          {/* 07 Simli Face ID */}
          <div>
            {sectionNum("07")}
            <label className={labelCls}>Simli Face ID (optional)</label>
            <input
              className={inputCls}
              placeholder="Paste face ID from app.simli.ai/create"
              value={simliId}
              onChange={(e) => setSimliId(e.target.value)}
            />
            <p className="mt-1 font-sans text-[10px] text-muted">
              Get a face ID at{" "}
              <a
                href="https://app.simli.ai/create"
                target="_blank"
                rel="noopener noreferrer"
                className="underline transition-colors hover:text-textdim"
              >
                app.simli.ai/create
              </a>
            </p>
          </div>

          {error && <p className="font-sans text-sm text-red">{error}</p>}

          <button
            className="group mt-1 w-full rounded-xl py-3 font-sans text-sm font-medium text-white transition-all disabled:opacity-40"
            style={{ background: busy ? "#52525B" : "#18181B" }}
            onClick={submit}
            disabled={busy}
          >
            {busy ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Building persona…
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5">
                {existingPersona ? "Update Persona" : "Bring them to life"}
                <span className="transition-transform duration-200 group-hover:translate-x-1">→</span>
              </span>
            )}
          </button>
        </div>
      )}

      {/* Camera modal overlay */}
      {cameraMode && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-accent/80 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-4">
            <p className="font-sans text-sm text-white/70">
              Position your face in the circle
            </p>
            <video
              ref={videoRef}
              className="h-64 w-64 rounded-full border-2 border-white/30 object-cover"
              autoPlay
              playsInline
              muted
            />
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={capturePhoto}
                className="rounded-lg bg-white px-6 py-2.5 font-sans text-sm font-medium text-accent transition-opacity hover:opacity-90"
              >
                Capture
              </button>
              <button
                type="button"
                onClick={cancelCamera}
                className="font-sans text-sm text-white/60 transition-colors hover:text-white"
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
