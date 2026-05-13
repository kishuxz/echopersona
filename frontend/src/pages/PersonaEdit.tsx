import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { PersonaUpload } from '../components/PersonaUpload'
import { useKeepAlive } from '../hooks/useKeepAlive'
import { getPersona } from '../lib/api'
import type { Persona } from '../types'

export function PersonaEdit() {
  useKeepAlive()
  const { personaId } = useParams<{ personaId: string }>()
  const navigate = useNavigate()
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

  const handleUpdated = (updated: Persona) => {
    navigate(`/dashboard/persona/${updated.id}`)
  }

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
      <div className="border-b border-border bg-surface px-6 py-3 shadow-card lg:px-10">
        <div className="mx-auto flex max-w-[1440px] items-center gap-4">
          <button
            className="font-sans text-sm text-muted transition-colors hover:text-text"
            onClick={() => navigate(`/dashboard/persona/${persona.id}`)}
          >
            ← Back
          </button>
          <span className="text-border">|</span>
          <span className="font-fraunces text-base font-semibold text-text">
            Edit — {persona.name}
          </span>
        </div>
      </div>
      <div className="mx-auto max-w-lg px-6 py-8">
        <PersonaUpload onPersona={handleUpdated} existingPersona={persona} />
      </div>
    </div>
  )
}
