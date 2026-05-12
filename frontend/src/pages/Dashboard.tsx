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
      <div className="flex items-center justify-between border-b border-border px-8 py-4">
        <div>
          <h1 className="font-mono text-xl font-bold uppercase tracking-[0.15em] text-green">
            EchoPersona
          </h1>
          <p className="font-mono text-[10px] text-textdim">{user?.email}</p>
        </div>
        <div className="flex items-center gap-4">
          <button
            className="rounded bg-green px-4 py-2 font-mono text-xs font-bold uppercase tracking-widest text-bg transition-opacity hover:opacity-90"
            onClick={() => setShowCreate(true)}
          >
            + New Persona
          </button>
          <button
            className="font-mono text-xs text-textdim transition-colors hover:text-text"
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
              <h2 className="font-mono text-xs uppercase tracking-widest text-textdim">
                Create Persona
              </h2>
              <button
                className="font-mono text-[10px] text-muted hover:text-text"
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

        <h2 className="mb-6 font-mono text-xs uppercase tracking-widest text-textdim">
          My Personas
        </h2>

        {error && (
          <p className="mb-4 font-mono text-xs text-red-400">{error}</p>
        )}

        {loading ? (
          <div className="flex items-center gap-2">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-20" cx="12" cy="12" r="10" stroke="#00ff88" strokeWidth="3" />
              <path className="opacity-80" fill="#00ff88" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="font-mono text-sm text-textdim">Loading personas…</span>
          </div>
        ) : personas.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border py-16 text-center">
            <p className="font-mono text-sm text-textdim">No personas yet.</p>
            <button
              className="mt-4 font-mono text-xs text-green underline"
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
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5 transition-colors hover:border-green/40">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-green/10 font-mono text-sm font-bold text-green">
          {initials}
        </div>
        <div className="min-w-0">
          <p className="font-mono text-sm font-bold text-text">{persona.name}</p>
          {createdDate && (
            <p className="mt-0.5 font-mono text-[10px] text-muted">{createdDate}</p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {persona.personality_traits.slice(0, 3).map((t) => (
          <span
            key={t}
            className="rounded border border-border px-2 py-0.5 font-mono text-[10px] text-textdim"
          >
            {t}
          </span>
        ))}
      </div>

      <div className="flex gap-1.5">
        <span
          className={`rounded-full px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider ${
            persona.voice_id
              ? 'bg-green/10 text-green'
              : 'bg-border text-muted'
          }`}
        >
          {persona.voice_id ? 'Voice Cloned' : 'Default Voice'}
        </span>
        <span className="rounded-full bg-border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-muted">
          {persona.stories.length} {persona.stories.length === 1 ? 'story' : 'stories'}
        </span>
      </div>

      <div className="flex gap-2 border-t border-border pt-3">
        <button
          className="flex-1 rounded bg-green py-2 font-mono text-xs font-bold uppercase tracking-widest text-bg transition-opacity hover:opacity-90"
          onClick={onTalk}
        >
          Talk Now
        </button>
        <button
          className="rounded border border-border px-3 py-2 font-mono text-xs text-muted transition-colors hover:border-red-500 hover:text-red-400"
          onClick={onDelete}
          title="Delete persona"
        >
          Delete
        </button>
      </div>
    </div>
  )
}
