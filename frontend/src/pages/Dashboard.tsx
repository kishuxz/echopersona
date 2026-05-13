import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PersonaUpload } from '../components/PersonaUpload'
import { useAuth } from '../hooks/useAuth'
import { useKeepAlive } from '../hooks/useKeepAlive'
import { deletePersona, listPersonas } from '../lib/api'
import type { Persona } from '../types'

export function Dashboard() {
  useKeepAlive()
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listPersonas()
      .then(setPersonas)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const handlePersonaCreated = (persona: Persona) => {
    setPersonas((prev) => [persona, ...prev])
    setShowCreate(false)
  }

  const handleDelete = async (id: string) => {
    await deletePersona(id)
    setPersonas((prev) => prev.filter((p) => p.id !== id))
  }

  const handleSignOut = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-bg text-text">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-surface px-8 py-4 shadow-card">
        <div>
          <h1 className="font-fraunces text-xl font-semibold text-text">
            EchoPersona
          </h1>
          <p className="font-sans text-xs text-muted">{user?.email}</p>
        </div>
        <div className="flex items-center gap-4">
          <button
            className="rounded-lg bg-accent px-4 py-2 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
            onClick={() => setShowCreate(true)}
          >
            + New Persona
          </button>
          <button
            className="font-sans text-sm text-textdim transition-colors hover:text-text"
            onClick={handleSignOut}
          >
            Sign Out
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-8 py-8">
        {showCreate && (
          <div className="mb-8">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-fraunces text-lg font-semibold text-text">
                Create Persona
              </h2>
              <button
                className="font-sans text-sm text-muted hover:text-textdim"
                onClick={() => setShowCreate(false)}
              >
                cancel
              </button>
            </div>
            <div className="max-w-md">
              <PersonaUpload onPersona={handlePersonaCreated} />
            </div>
          </div>
        )}

        <h2 className="mb-6 font-sans text-xs font-medium uppercase tracking-widest text-muted">
          My Personas
        </h2>

        {error && (
          <p className="mb-4 font-sans text-sm text-red">{error}</p>
        )}

        {loading ? (
          <div className="flex items-center gap-2">
            <svg className="h-4 w-4 animate-spin text-green" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="font-sans text-sm text-textdim">Loading personas…</span>
          </div>
        ) : personas.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-surface py-16 text-center shadow-card">
            <p className="font-sans text-sm text-textdim">No personas yet.</p>
            <button
              className="mt-4 font-sans text-sm text-green underline"
              onClick={() => setShowCreate(true)}
            >
              Create your first persona →
            </button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {personas.map((p) => (
              <PersonaCard
                key={p.id}
                persona={p}
                onTalk={() => navigate(`/dashboard/persona/${p.id}`)}
                onDelete={() => handleDelete(p.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function PersonaCard({
  persona,
  onTalk,
  onDelete,
}: {
  persona: Persona
  onTalk: () => void
  onDelete: () => void
}) {
  const initials = persona.name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  const createdDate = persona.created_at
    ? new Date(persona.created_at).toLocaleDateString()
    : ''

  return (
    <div className="card-hover flex flex-col gap-4 rounded-xl border border-border bg-surface p-5 shadow-card">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-cream font-sans text-sm font-semibold text-text">
          {initials}
        </div>
        <div className="min-w-0">
          <p className="font-sans text-sm font-semibold text-text">{persona.name}</p>
          {createdDate && (
            <p className="mt-0.5 font-mono text-[10px] text-muted">{createdDate}</p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {persona.personality_traits.slice(0, 3).map((t) => (
          <span
            key={t}
            className="rounded-full bg-cream px-2.5 py-0.5 font-sans text-[11px] text-textdim"
          >
            {t}
          </span>
        ))}
      </div>

      <div className="flex gap-1.5">
        <span
          className={`rounded-full px-2.5 py-0.5 font-sans text-[10px] ${
            persona.voice_id
              ? 'bg-green/10 text-green'
              : 'bg-cream text-muted'
          }`}
        >
          {persona.voice_id ? 'Voice Cloned' : 'Default Voice'}
        </span>
        <span className="rounded-full bg-cream px-2.5 py-0.5 font-sans text-[10px] text-muted">
          {persona.stories.length} {persona.stories.length === 1 ? 'story' : 'stories'}
        </span>
      </div>

      <div className="flex gap-2 border-t border-border pt-3">
        <button
          className="flex-1 rounded-lg bg-accent py-2 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
          onClick={onTalk}
        >
          Talk Now
        </button>
        <button
          className="rounded-lg border border-border px-3 py-2 font-sans text-sm text-muted transition-colors hover:border-red hover:text-red"
          onClick={onDelete}
          title="Delete persona"
        >
          Delete
        </button>
      </div>
    </div>
  )
}
