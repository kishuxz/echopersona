import { Plus, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { createPersona, uploadAvatar, uploadVoice } from "../lib/api";
import type { Persona } from "../types";

interface PersonaUploadProps {
  onPersona: (persona: Persona) => void;
  activePersona?: Persona | null;
}

export function PersonaUpload({ onPersona, activePersona }: PersonaUploadProps) {
  const [name,   setName]   = useState("Demo Persona");
  const [stories, setStories] = useState(["They love explaining technical systems clearly and briefly."]);
  const [traits, setTraits]  = useState("warm, direct, technical");
  const [style,  setStyle]   = useState("short sentences, calm pacing");
  const [files,  setFiles]   = useState<FileList | null>(null);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [busy,   setBusy]    = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<"idle" | "cloning" | "cloned" | "error">("idle");
  const [error,  setError]   = useState<string | null>(null);
  const [showForm, setShowForm] = useState(true);

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

      if (files?.length) {
        setVoiceStatus("cloning");
        try {
          persona = await uploadVoice(persona.id, files);
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

  const inputCls =
    "w-full rounded border border-border bg-bg px-3 py-2 font-sans text-sm text-text placeholder:text-muted outline-none transition-colors focus:border-green";
  const labelCls = "block font-mono text-[10px] uppercase tracking-widest text-textdim mb-1";

  return (
    <div className="rounded-lg border border-border bg-surface">
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
          <div>
            <label className={labelCls}>Name</label>
            <input
              className={inputCls}
              placeholder="e.g. David Letterman"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div>
            <label className={labelCls}>Personality traits</label>
            <textarea
              className={inputCls + " min-h-[60px] resize-y"}
              placeholder="e.g. sarcastic, witty, loves comedy"
              value={traits}
              onChange={(e) => setTraits(e.target.value)}
            />
          </div>

          <div>
            <label className={labelCls}>Speaking style</label>
            <textarea
              className={inputCls + " min-h-[60px] resize-y"}
              placeholder="e.g. dry humor, long pauses"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
            />
          </div>

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

          <div>
            <label className={labelCls}>Voice samples (optional)</label>
            <label className="flex cursor-pointer flex-col items-center gap-2 rounded border-2 border-dashed border-border py-4 transition-colors hover:border-green hover:bg-green/[0.03]">
              <Upload size={18} className="text-textdim" />
              <span className="font-mono text-[10px] text-textdim">
                {files?.length ? `${files.length} file(s) selected` : "Drop audio files here"}
              </span>
              <input
                type="file"
                accept="audio/*"
                multiple
                className="hidden"
                onChange={(e) => { setFiles(e.target.files); setVoiceStatus("idle"); }}
              />
            </label>
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

          {/* Avatar image upload */}
          <div>
            <label className={labelCls}>Face photo for video avatar (optional)</label>
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
          </div>

          {error && (
            <p className="font-mono text-[10px] text-red">{error}</p>
          )}

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
    </div>
  );
}
