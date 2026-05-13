import { useMemo, useState } from "react";
import { LatencyDashboard } from "./components/LatencyDashboard";
import { PersonaUpload } from "./components/PersonaUpload";
import { VoiceInterface } from "./components/VoiceInterface";
import { useLatencyTracker } from "./hooks/useLatencyTracker";
import type { Persona } from "./types";
import "./styles.css";

export default function App() {
  const sessionId = useMemo(() => crypto.randomUUID(), []);
  const [persona, setPersona] = useState<Persona | null>(null);
  const { snapshots, addSnapshot } = useLatencyTracker();

  return (
    <div className="relative min-h-screen bg-[#080808] font-sans" style={{ color: "#f0f0f0" }}>

      {/* ── Navigation ── */}
      <header className="sticky top-0 z-40 border-b border-[#141414] bg-[#080808]/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between px-6 py-3.5 lg:px-10">
          <div className="flex items-center gap-3">
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green opacity-60" />
              <span className="relative h-2 w-2 rounded-full bg-green" />
            </span>
            <span className="font-mono text-sm font-bold uppercase tracking-[0.3em] text-green">Echo</span>
            <span className="font-mono text-xs text-[#242424]">/</span>
            <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#383838]">Persona</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden font-mono text-[10px] text-[#2c2c2c] sm:block">kramkum@iu.edu</span>
            <div className="h-3 w-px bg-[#1c1c1c]" />
            <span className="rounded border border-[#1c1c1c] bg-[#0c0c0c] px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest text-[#363636]">
              v0.1
            </span>
          </div>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="relative z-10 mx-auto max-w-[1440px] px-6 py-8 lg:px-10">

        {/* Page heading */}
        <div className="mb-8 panel-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-[#272727]">Real-time AI</p>
          <h1 className="font-mono text-3xl font-bold uppercase tracking-[0.12em] text-[#e8e8e8]">
            EchoPersona
          </h1>
          <p className="mt-1.5 font-sans text-sm text-[#424242]">
            Conversational AI avatars with sub-600ms latency
          </p>
        </div>

        {/* ── Two-column layout ── */}
        <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">

          {/* Left column (40%) */}
          <div className="flex flex-col gap-5 panel-2 lg:w-[40%]">
            <PersonaUpload onPersona={setPersona} activePersona={persona} />
          </div>

          {/* Right column (60%) */}
          <div className="flex flex-col gap-5 panel-3 lg:w-[60%]">
            <LatencyDashboard snapshots={snapshots} />
            <div className="flex flex-1 flex-col">
              <VoiceInterface
                sessionId={sessionId}
                personaId={persona?.id}
                idleVideoUrl={persona?.idle_video_url}
                onLatencyUpdate={addSnapshot}
              />
            </div>
          </div>

        </div>
      </main>
    </div>
  );
}
