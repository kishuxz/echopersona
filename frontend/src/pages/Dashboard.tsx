import { Pencil } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CreationWizard } from '../components/CreationWizard'
import { useAuth } from '../hooks/useAuth'
import { useKeepAlive } from '../hooks/useKeepAlive'
import { createPersona, deletePersona, listPersonas } from '../lib/api'
import type { Persona, PersonaCreate } from '../types'

export function Dashboard() {
  useKeepAlive()
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [loading, setLoading] = useState(true)
  const [createStep, setCreateStep] = useState<'idle' | 'shell' | 'interview'>('idle')
  const [newPersonaId, setNewPersonaId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadPersonas = useCallback(() => {
    setLoading(true)
    setError(null)
    listPersonas()
      .then(setPersonas)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load personas'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadPersonas() }, [loadPersonas])

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Delete "${name}"? This cannot be undone.`)) return
    try {
      await deletePersona(id)
      setPersonas((prev) => prev.filter((p) => p.id !== id))
    } catch {
      setError('Failed to delete persona. Please try again.')
    }
  }

  const handleSignOut = async () => {
    await signOut()
    navigate('/login')
  }

  const rawName: string =
    (user?.user_metadata?.full_name as string | undefined) ||
    user?.email?.split('@')[0]?.split('.')[0] ||
    ''
  const displayName = rawName.charAt(0).toUpperCase() + rawName.slice(1)
  const isInterviewing = createStep === 'interview'

  return (
    <div className="min-h-screen bg-bg text-text">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-y-2 border-b border-border bg-surface px-6 py-4 shadow-card lg:px-8">
        <div>
          <div className="flex items-center gap-3">
            <button
              className="font-sans text-sm text-muted transition-colors hover:text-text"
              onClick={() => navigate('/')}
            >
              ← Home
            </button>
            <span className="text-border">|</span>
            <h1 className="font-fraunces text-xl font-semibold text-text">
              EchoPersona
            </h1>
          </div>
          {displayName && (
            <p className="mt-0.5 font-fraunces text-sm italic text-textdim">
              Welcome back, {displayName}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {!isInterviewing && (
            <button
              className="btn-shimmer rounded-lg px-4 py-2 font-sans text-sm font-medium text-white"
              onClick={() => setCreateStep('shell')}
            >
              + New Persona
            </button>
          )}
          <button
            className="font-sans text-sm text-textdim transition-colors hover:text-text"
            onClick={() => navigate('/dashboard/billing')}
          >
            Billing
          </button>
          <button
            className="font-sans text-sm text-textdim transition-colors hover:text-text"
            onClick={handleSignOut}
          >
            Sign Out
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8">
        {/* ── Creation flow ─────────────────────────────────────────── */}
        {createStep !== 'idle' && (
          <div className={isInterviewing ? 'mb-0' : 'mb-10'}>
            {createStep === 'shell' && (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="font-fraunces text-lg font-semibold text-text">
                    Create a new persona
                  </h2>
                  <button
                    className="font-sans text-sm text-muted underline transition-colors hover:text-text"
                    onClick={() => setCreateStep('idle')}
                  >
                    Cancel
                  </button>
                </div>
                <div className="max-w-lg">
                  <PersonaShellForm
                    onCreated={(personaId) => {
                      setNewPersonaId(personaId)
                      setCreateStep('interview')
                    }}
                    onCancel={() => setCreateStep('idle')}
                  />
                </div>
              </>
            )}
            {isInterviewing && newPersonaId && (
              <div className="mx-auto max-w-2xl">
                <div className="mb-5 flex items-center justify-between">
                  <h2 className="font-fraunces text-lg font-semibold text-text">
                    Tell us their story
                  </h2>
                  <button
                    className="font-sans text-sm text-muted underline transition-colors hover:text-text"
                    onClick={() => setCreateStep('idle')}
                  >
                    Save & exit
                  </button>
                </div>
                <CreationWizard
                  personaId={newPersonaId}
                  onComplete={(personaId) => {
                    setCreateStep('idle')
                    navigate(`/dashboard/persona/${personaId}`)
                  }}
                />
              </div>
            )}
          </div>
        )}

        {/* ── Personas list (hidden during interview) ───────────────── */}
        {!isInterviewing && (
          <>
            <h2 className="mb-6 font-sans text-xs font-medium uppercase tracking-widest text-muted">
              My Personas
            </h2>

            {error && (
              <div className="mb-6 flex items-center gap-3 rounded-xl border border-red/20 bg-red/5 px-5 py-4">
                <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5 shrink-0 text-red">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                <p className="flex-1 font-sans text-sm text-red">{error}</p>
                <button
                  className="rounded-lg border border-red/20 px-4 py-1.5 font-sans text-xs font-medium text-red transition-colors hover:bg-red/10"
                  onClick={loadPersonas}
                >
                  Retry
                </button>
              </div>
            )}

            {loading ? (
              <div className="flex items-center gap-2 py-8">
                <svg className="h-4 w-4 animate-spin text-accent" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span className="font-sans text-sm text-textdim">Loading personas…</span>
              </div>
            ) : !error && personas.length === 0 ? (
              <EmptyState onCreate={() => setCreateStep('shell')} />
            ) : personas.length > 0 ? (
              <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                {personas.map((p) => (
                  <PersonaCard
                    key={p.id}
                    persona={p}
                    onTalk={() => navigate(`/dashboard/persona/${p.id}`)}
                    onEdit={() => navigate(`/dashboard/persona/${p.id}/edit`)}
                    onDelete={() => handleDelete(p.id, p.name)}
                  />
                ))}
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-surface py-20 text-center shadow-card">
      <svg width="64" height="48" viewBox="0 0 64 48" fill="none" className="mb-6 text-border">
        <rect x="0" y="8" width="36" height="24" rx="10" fill="currentColor" />
        <path d="M10 32 L6 40 L18 32" fill="currentColor" />
        <rect x="20" y="0" width="44" height="24" rx="10" fill="#E4E4E7" />
        <path d="M54 24 L58 32 L46 24" fill="#E4E4E7" />
      </svg>
      <h3 className="font-fraunces text-xl font-semibold text-text">Ready to preserve a voice</h3>
      <p className="mt-2 max-w-xs font-sans text-sm text-textdim">
        Create a persona from someone's stories, personality, and memories
      </p>
      <button
        className="mt-6 rounded-lg bg-accent px-6 py-2.5 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
        onClick={onCreate}
      >
        Create your first persona →
      </button>
    </div>
  )
}

function PersonaCard({
  persona,
  onTalk,
  onEdit,
  onDelete,
}: {
  persona: Persona
  onTalk: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const [deleteHovered, setDeleteHovered] = useState(false)

  const initials = persona.name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  const hasPhoto = Boolean(persona.did_avatar_url)

  return (
    <div
      className="group relative flex flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-card transition-all duration-200 hover:scale-[1.02] hover:shadow-card-hover"
      style={{ minHeight: '220px' }}
    >
      {hasPhoto ? (
        <div className="relative flex-1">
          <img
            src={persona.did_avatar_url!}
            alt={persona.name}
            className="absolute inset-0 h-full w-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />

          <div className="relative flex h-full flex-col justify-end p-5" style={{ minHeight: '220px' }}>
            <button
              className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full bg-black/40 text-white/70 opacity-0 transition-all duration-150 hover:bg-red/80 hover:text-white group-hover:opacity-100"
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              title="Delete persona"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14H6L5 6" />
                <path d="M10 11v6M14 11v6" />
                <path d="M9 6V4h6v2" />
              </svg>
            </button>

            <div className="mb-2 flex flex-wrap gap-1.5">
              {persona.personality_traits.slice(0, 3).map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-white/20 px-2.5 py-0.5 font-sans text-[10px] text-white/90 backdrop-blur-sm"
                >
                  {t}
                </span>
              ))}
            </div>

            <h3 className="font-fraunces text-2xl font-semibold text-white">{persona.name}</h3>

            <div className="mt-1.5 flex items-center gap-2">
              {persona.voice_id && (
                <span className="rounded-full bg-green/80 px-2.5 py-0.5 font-sans text-[10px] text-white">
                  Voice Cloned
                </span>
              )}
              <span className="font-sans text-[10px] text-white/60">
                {persona.stories.length} {persona.stories.length === 1 ? 'memory' : 'memories'}
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div className="relative flex flex-1 flex-col" style={{ minHeight: '220px' }}>
          <div className="flex flex-1 items-center justify-center bg-gradient-to-br from-cream via-elevated to-surface">
            <span className="font-fraunces text-5xl font-semibold text-text/20">{initials}</span>
          </div>

          <button
            className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full bg-elevated text-muted opacity-0 transition-all duration-150 hover:bg-red/10 hover:text-red group-hover:opacity-100"
            onMouseEnter={() => setDeleteHovered(true)}
            onMouseLeave={() => setDeleteHovered(false)}
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            title="Delete persona"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14H6L5 6" />
              <path d="M10 11v6M14 11v6" />
              <path d="M9 6V4h6v2" />
            </svg>
          </button>

          <div className="border-t border-border px-5 pb-3 pt-3">
            <div className="flex flex-wrap gap-1.5 mb-2">
              {persona.personality_traits.slice(0, 3).map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-cream px-2.5 py-0.5 font-sans text-[10px] text-textdim"
                >
                  {t}
                </span>
              ))}
            </div>
            <h3 className="font-fraunces text-xl font-semibold text-text">{persona.name}</h3>
            <div className="mt-1 flex items-center gap-2">
              {persona.voice_id && (
                <span className="rounded-full bg-green/10 px-2.5 py-0.5 font-sans text-[10px] text-green">
                  Voice Cloned
                </span>
              )}
              <span className="font-sans text-[10px] text-muted">
                {persona.stories.length} {persona.stories.length === 1 ? 'memory' : 'memories'}
              </span>
            </div>
          </div>
        </div>
      )}

      <div className="flex">
        <button
          className="flex-1 bg-accent py-3 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
          onClick={onTalk}
        >
          Talk Now
        </button>
        <button
          className="flex items-center gap-1 border-l border-white/20 bg-accent px-4 py-3 font-sans text-sm font-medium text-white/80 transition-all hover:bg-accent/80 hover:text-white"
          onClick={(e) => { e.stopPropagation(); onEdit(); }}
          title="Edit persona"
        >
          <Pencil size={13} />
        </button>
      </div>
    </div>
  )
}

function PersonaShellForm({
  onCreated,
  onCancel,
}: {
  onCreated: (personaId: string) => void
  onCancel: () => void
}) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (name.trim().length < 2) {
      setError('Please enter a name (at least 2 characters).')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const data: PersonaCreate = { name: name.trim(), stories: [], personality_traits: [], speaking_style: '' }
      const persona = await createPersona(data)
      onCreated(persona.id)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create persona')
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-border bg-surface p-6 shadow-card">
      <p className="mb-4 font-sans text-sm text-textdim">
        Who would you like to preserve? Give them a name to get started.
      </p>
      <label className="mb-1 block font-sans text-xs font-medium uppercase tracking-widest text-muted">
        Name
      </label>
      <input
        type="text"
        className="w-full rounded-lg border border-border bg-bg px-3 py-2.5 font-sans text-sm text-text placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/30"
        placeholder="e.g. Grandma Rose"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
        disabled={busy}
      />
      {error && <p className="mt-2 font-sans text-xs text-red">{error}</p>}
      <div className="mt-4 flex items-center gap-3">
        <button
          type="submit"
          className="rounded-lg bg-accent px-5 py-2.5 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          disabled={busy || name.trim().length < 2}
        >
          {busy ? 'Creating…' : 'Begin →'}
        </button>
        <button
          type="button"
          className="font-sans text-sm text-muted transition-colors hover:text-text"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </button>
      </div>
    </form>
  )
}
