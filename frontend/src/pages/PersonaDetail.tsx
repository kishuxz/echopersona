import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { LatencyDashboard } from '../components/LatencyDashboard'
import { VoiceInterface } from '../components/VoiceInterface'
import { useKeepAlive } from '../hooks/useKeepAlive'
import { useLatencyTracker } from '../hooks/useLatencyTracker'
import { getPersona } from '../lib/api'
import type { Persona } from '../types'

export function PersonaDetail() {
  useKeepAlive()
  const { personaId } = useParams<{ personaId: string }>()
  const navigate = useNavigate()
  const sessionId = useMemo(() => crypto.randomUUID(), [])
  const { snapshots, addSnapshot } = useLatencyTracker()
  const [persona, setPersona] = useState<Persona | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!personaId) return
    getPersona(personaId)
      .then(setPersona)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [personaId])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="flex items-center gap-3">
          <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-20" cx="12" cy="12" r="10" stroke="#00ff88" strokeWidth="3" />
            <path className="opacity-80" fill="#00ff88" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="font-mono text-sm text-textdim">Loading…</span>
        </div>
      </div>
    )
  }

  if (error || !persona) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="text-center">
          <p className="font-mono text-sm text-red-400">{error ?? 'Persona not found'}</p>
          <button
            className="mt-4 font-mono text-xs text-green underline"
            onClick={() => navigate('/dashboard')}
          >
            ← Back to dashboard
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg font-sans text-text">
      {/* Header bar */}
      <div className="border-b border-border px-6 py-3 lg:px-10">
        <div className="mx-auto flex max-w-[1440px] items-center gap-4">
          <button
            className="font-mono text-[10px] uppercase tracking-widest text-textdim transition-colors hover:text-green"
            onClick={() => navigate('/dashboard')}
          >
            ← Dashboard
          </button>
          <span className="text-border">|</span>
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-bold text-green">{persona.name}</span>
            <span className="font-mono text-[10px] text-textdim">·</span>
            <span className="font-mono text-[10px] text-textdim">{persona.speaking_style}</span>
          </div>
          <div className="ml-auto flex flex-wrap gap-1">
            {persona.personality_traits.slice(0, 4).map((t) => (
              <span
                key={t}
                className="rounded border border-border px-2 py-0.5 font-mono text-[9px] text-muted"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="mx-auto max-w-[1440px] px-6 py-6 lg:px-10">
        <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
          {/* Left: latency dashboard */}
          <div className="lg:w-[38%]">
            <LatencyDashboard snapshots={snapshots} />
          </div>

          {/* Right: voice interface */}
          <div className="flex-1">
            <VoiceInterface
              sessionId={sessionId}
              personaId={persona.id}
              personaName={persona.name}
              onLatencyUpdate={addSnapshot}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
