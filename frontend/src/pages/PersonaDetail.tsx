import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
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
  const { addSnapshot } = useLatencyTracker()
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
          <svg className="h-5 w-5 animate-spin text-green" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
            <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="font-sans text-sm text-textdim">Loading…</span>
        </div>
      </div>
    )
  }

  if (error || !persona) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="text-center">
          <p className="font-sans text-sm text-red">{error ?? 'Persona not found'}</p>
          <button
            className="mt-4 font-sans text-sm text-green underline"
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
      {/* Header */}
      <div className="border-b border-border bg-surface shadow-card">
        {/* Top nav */}
        <div className="px-6 py-3 lg:px-10">
          <div className="mx-auto max-w-[1440px]">
            <button
              className="font-sans text-sm text-muted transition-colors hover:text-text"
              onClick={() => navigate('/dashboard')}
            >
              ← Dashboard
            </button>
          </div>
        </div>

        {/* Persona summary strip */}
        <div className="border-t border-border/50 px-6 pb-4 pt-3 lg:px-10">
          <div className="mx-auto flex max-w-[1440px] flex-wrap items-start justify-between gap-4">
            {/* Left: name + style + badges */}
            <div className="flex flex-col gap-1.5">
              <h1 className="font-fraunces text-2xl font-semibold text-text">{persona.name}</h1>
              {persona.speaking_style && (
                <p className="font-sans text-sm text-muted">{persona.speaking_style}</p>
              )}
              <div className="mt-1 flex flex-wrap items-center gap-2">
                {persona.personality_traits?.slice(0, 3).map((t) => (
                  <span key={t} className="rounded-full bg-cream px-2.5 py-0.5 font-sans text-[10px] text-textdim">
                    {t}
                  </span>
                ))}
                {persona.voice_id && (
                  <span className="rounded-full bg-green/10 px-2.5 py-0.5 font-sans text-[10px] text-green">
                    Voice Cloned
                  </span>
                )}
                {persona.stories.length > 0 && (
                  <span className="rounded-full bg-cream px-2.5 py-0.5 font-sans text-[10px] text-textdim">
                    {persona.stories.length} {persona.stories.length === 1 ? 'memory' : 'memories'}
                  </span>
                )}
              </div>
            </div>

            {/* Right: Consent & Succession button */}
            <button
              className="rounded-lg border border-border px-3.5 py-2 font-sans text-sm text-textdim transition-colors hover:border-border-hi hover:text-text"
              onClick={() => navigate(`/dashboard/persona/${personaId}/consent`)}
            >
              Consent &amp; Succession →
            </button>
          </div>
        </div>
      </div>

      {/* Main content — full width voice interface */}
      <div className="mx-auto max-w-[1200px] px-6 py-6 lg:px-10">
        <VoiceInterface
          sessionId={sessionId}
          personaId={persona.id}
          personaName={persona.name}
          personaTraits={persona.personality_traits}
          storyCount={persona.stories.length}
          hasVoice={Boolean(persona.voice_id)}
          idleVideoUrl={persona.idle_video_url}
          avatarUrl={persona.did_avatar_url}
          onLatencyUpdate={addSnapshot}
        />
      </div>
    </div>
  )
}
