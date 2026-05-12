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
    <div className="min-h-screen bg-bg font-sans text-text">
      <div className="mx-auto max-w-[1440px] px-6 py-8 lg:px-10">

        {/* ── Two-column layout ── */}
        <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">

          {/* ── Left column (40%) ── */}
          <div className="flex flex-col gap-5 lg:w-[40%]">

            {/* Wordmark */}
            <div className="mb-2">
              <p className="font-mono text-xs uppercase tracking-[0.25em] text-textdim">System</p>
              <h1 className="font-mono text-2xl font-bold uppercase tracking-[0.15em] text-green">
                EchoPersona
              </h1>
              <p className="mt-1 font-sans text-sm text-textdim">
                Real-time conversational AI personas
              </p>
            </div>

            {/* Persona panel */}
            <PersonaUpload onPersona={setPersona} activePersona={persona} />
          </div>

          {/* ── Right column (60%) ── */}
          <div className="flex flex-col gap-5 lg:w-[60%]">
            <LatencyDashboard snapshots={snapshots} />
            <div className="flex flex-1 flex-col">
              <VoiceInterface
                sessionId={sessionId}
                personaId={persona?.id}
                onLatencyUpdate={addSnapshot}
              />
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
