import { useMemo, useState } from "react";
import { PersonaUpload } from "./components/PersonaUpload";
import { VoiceInterface } from "./components/VoiceInterface";
import { useLatencyTracker } from "./hooks/useLatencyTracker";
import type { Persona } from "./types";
import "./styles.css";

export default function App() {
  const sessionId = useMemo(() => crypto.randomUUID(), []);
  const [persona, setPersona] = useState<Persona | null>(null);
  const { addSnapshot } = useLatencyTracker();

  return (
    <div className="relative min-h-screen bg-bg font-sans text-text">

      {/* ── Navigation ── */}
      <header className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur-md shadow-card">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between px-6 py-3.5 lg:px-10">
          <span className="font-fraunces text-lg font-semibold text-text">EchoPersona</span>
          <div className="flex items-center gap-3">
            <span className="rounded border border-border bg-elevated px-2 py-0.5 font-mono text-[10px] text-muted">
              v0.1
            </span>
          </div>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="relative z-10 mx-auto max-w-[1440px] px-6 py-8 lg:px-10">

        <div className="mb-8">
          <h1 className="font-fraunces text-3xl font-semibold text-text">EchoPersona</h1>
          <p className="mt-1.5 font-sans text-sm text-textdim">
            Conversational AI avatars with real-time voice
          </p>
        </div>

        {/* ── Two-column layout ── */}
        <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">

          {/* Left column (40%) */}
          <div className="flex flex-col gap-5 lg:w-[40%]">
            <PersonaUpload onPersona={setPersona} activePersona={persona} />
          </div>

          {/* Right column (60%) */}
          <div className="flex flex-col gap-5 lg:w-[60%]">
            <VoiceInterface
              sessionId={sessionId}
              personaId={persona?.id}
              personaName={persona?.name}
              personaTraits={persona?.personality_traits}
              storyCount={persona?.stories.length}
              idleVideoUrl={persona?.idle_video_url}
              avatarUrl={persona?.did_avatar_url}
              onLatencyUpdate={addSnapshot}
            />
          </div>

        </div>
      </main>
    </div>
  );
}
