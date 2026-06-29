import { useCallback, useEffect, useState } from 'react'
import type {
  AdminPersonaDetail,
  AdminPersonaRow,
  AdminRelationship,
  AdminRelationshipCreate,
  AdminStats,
} from '../types'
import {
  adminAddRelationship,
  adminGetPersona,
  adminGetStats,
  adminListPersonas,
  adminReEnrich,
  adminRemoveRelationship,
} from '../lib/adminApi'

// ── Key guard ─────────────────────────────────────────────────────────────────

function useAdminKey() {
  const [key, setKey] = useState<string>(() => localStorage.getItem('adminKey') ?? '')
  const [valid, setValid] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState('')

  const submit = useCallback(async (k: string) => {
    setChecking(true)
    setError('')
    localStorage.setItem('adminKey', k)
    setKey(k)
    try {
      await adminGetStats()
      setValid(true)
    } catch {
      localStorage.removeItem('adminKey')
      setKey('')
      setError('Invalid key')
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    if (key) submit(key)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return { key, valid, checking, error, submit, setKey }
}

// ── KeyForm ───────────────────────────────────────────────────────────────────

function KeyForm({
  checking,
  error,
  onSubmit,
}: {
  checking: boolean
  error: string
  onSubmit: (k: string) => void
}) {
  const [input, setInput] = useState('')
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-bg">
      <span className="font-fraunces text-2xl font-semibold text-text">EchoPersona Admin</span>
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit(input)
        }}
      >
        <input
          type="password"
          placeholder="Admin key"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="rounded-lg border border-border bg-surface px-4 py-2 font-mono text-sm text-text outline-none focus:border-accent"
        />
        {error && <p className="font-sans text-xs text-red-500">{error}</p>}
        <button
          type="submit"
          disabled={checking || !input}
          className="rounded-lg bg-accent px-4 py-2 font-sans text-sm font-medium text-white disabled:opacity-50"
        >
          {checking ? 'Checking…' : 'Enter'}
        </button>
      </form>
    </div>
  )
}

// ── StatsBar ──────────────────────────────────────────────────────────────────

function StatsBar({ stats }: { stats: AdminStats }) {
  const cards: { label: string; value: number }[] = [
    { label: 'Personas', value: stats.total_personas },
    { label: 'Users', value: stats.total_users },
    { label: 'Memory Units', value: stats.total_memory_units },
    { label: 'Relationships', value: stats.total_relationships },
  ]
  return (
    <div className="flex gap-4">
      {cards.map((c) => (
        <div key={c.label} className="flex flex-col gap-1 rounded-lg border border-border bg-surface px-5 py-3">
          <span className="font-sans text-2xl font-bold text-text">{c.value}</span>
          <span className="font-sans text-xs text-textdim">{c.label}</span>
        </div>
      ))}
      <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface px-5 py-3">
        <span className="font-sans text-sm font-semibold text-text">By status</span>
        {Object.entries(stats.by_readiness).map(([k, v]) => (
          <span key={k} className="font-mono text-xs text-textdim">
            {k}: {v}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── PersonaTable ──────────────────────────────────────────────────────────────

function PersonaTable({
  rows,
  onSelect,
}: {
  rows: AdminPersonaRow[]
  onSelect: (id: string) => void
}) {
  const statusColor = (s: string) => {
    if (s === 'ready') return 'text-green-600'
    if (s === 'processing') return 'text-yellow-500'
    if (s === 'failed') return 'text-red-500'
    return 'text-textdim'
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full font-sans text-sm">
        <thead>
          <tr className="border-b border-border bg-surface">
            {['Name', 'Owner', 'Plan', 'Status', 'Mem', 'Rel', ''].map((h) => (
              <th key={h} className="px-4 py-2 text-left font-semibold text-textdim">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-border last:border-0 hover:bg-surface/50">
              <td className="px-4 py-2 font-medium text-text">{r.name}</td>
              <td className="px-4 py-2 text-textdim">{r.owner_email || '—'}</td>
              <td className="px-4 py-2">
                <span className="rounded bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
                  {r.plan_tier}
                </span>
              </td>
              <td className={`px-4 py-2 font-mono text-xs ${statusColor(r.readiness_status)}`}>
                {r.readiness_status}
              </td>
              <td className="px-4 py-2 text-textdim">{r.memory_unit_count}</td>
              <td className="px-4 py-2 text-textdim">{r.relationship_count}</td>
              <td className="px-4 py-2">
                <button
                  className="font-sans text-xs text-accent hover:underline"
                  onClick={() => onSelect(r.id)}
                >
                  View
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── PersonaDetail panel ───────────────────────────────────────────────────────

function AddRelationshipForm({
  personaId,
  onAdded,
}: {
  personaId: string
  onAdded: (r: AdminRelationship) => void
}) {
  const [form, setForm] = useState<AdminRelationshipCreate>({
    listener_user_id: '',
    entity_canonical: '',
    relationship: '',
    address_term: '',
  })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const submit = async () => {
    setSaving(true)
    setErr('')
    try {
      const r = await adminAddRelationship(personaId, form)
      onAdded(r)
      setForm({ listener_user_id: '', entity_canonical: '', relationship: '', address_term: '' })
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed')
    } finally {
      setSaving(false)
    }
  }

  const fields: { key: keyof AdminRelationshipCreate; placeholder: string }[] = [
    { key: 'listener_user_id', placeholder: 'Listener user UUID' },
    { key: 'entity_canonical', placeholder: 'Entity (e.g. John)' },
    { key: 'relationship', placeholder: 'Relationship (e.g. son)' },
    { key: 'address_term', placeholder: 'Address term (e.g. Dad)' },
  ]

  return (
    <div className="mt-2 flex flex-wrap items-end gap-2">
      {fields.map((f) => (
        <input
          key={f.key}
          placeholder={f.placeholder}
          value={form[f.key] ?? ''}
          onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
          className="rounded border border-border bg-surface px-3 py-1.5 font-mono text-xs text-text outline-none focus:border-accent"
        />
      ))}
      <button
        onClick={submit}
        disabled={saving || !form.listener_user_id || !form.relationship}
        className="rounded bg-accent px-3 py-1.5 font-sans text-xs font-medium text-white disabled:opacity-50"
      >
        {saving ? 'Adding…' : 'Add'}
      </button>
      {err && <span className="font-sans text-xs text-red-500">{err}</span>}
    </div>
  )
}

function PersonaDetailPanel({
  personaId,
  onClose,
}: {
  personaId: string
  onClose: () => void
}) {
  const [detail, setDetail] = useState<AdminPersonaDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [reenriching, setReenriching] = useState(false)
  const [reenrichMsg, setReenrichMsg] = useState('')

  useEffect(() => {
    setLoading(true)
    adminGetPersona(personaId)
      .then(setDetail)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [personaId])

  const handleReEnrich = async () => {
    setReenriching(true)
    setReenrichMsg('')
    try {
      const r = await adminReEnrich(personaId)
      setReenrichMsg(r.job_id ? `Queued: ${r.job_id}` : 'Queued (no job id)')
    } catch (e) {
      setReenrichMsg(e instanceof Error ? e.message : 'Failed')
    } finally {
      setReenriching(false)
    }
  }

  const handleRemoveRelationship = async (listenerUserId: string) => {
    if (!detail) return
    await adminRemoveRelationship(personaId, listenerUserId)
    setDetail((prev) =>
      prev
        ? { ...prev, relationships: prev.relationships.filter((r) => r.listener_user_id !== listenerUserId) }
        : prev,
    )
  }

  const handleRelationshipAdded = (r: AdminRelationship) => {
    setDetail((prev) => (prev ? { ...prev, relationships: [...prev.relationships, r] } : prev))
  }

  if (loading) return <p className="font-sans text-sm text-textdim">Loading…</p>
  if (err) return <p className="font-sans text-sm text-red-500">{err}</p>
  if (!detail) return null

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex items-center gap-4">
        <button onClick={onClose} className="font-sans text-sm text-textdim hover:text-text">
          ← Back
        </button>
        <span className="font-fraunces text-lg font-semibold text-text">{detail.name}</span>
        <span className="rounded bg-accent/10 px-2 py-0.5 font-sans text-xs font-medium text-accent">
          {detail.plan_tier}
        </span>
        <span className="font-mono text-xs text-textdim">{detail.readiness_status}</span>
      </div>

      {/* Info */}
      <div className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-surface p-4 font-sans text-sm">
        <div><span className="text-textdim">Owner: </span>{detail.owner_email}</div>
        <div><span className="text-textdim">Tone: </span>{detail.tone || '—'}</div>
        <div><span className="text-textdim">Answer pref: </span>{detail.answer_length_pref || '—'}</div>
        <div><span className="text-textdim">Tavus replica: </span>{detail.tavus_replica_id || '—'}</div>
      </div>

      {/* Re-enrich */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleReEnrich}
          disabled={reenriching}
          className="rounded bg-accent px-4 py-2 font-sans text-sm font-medium text-white disabled:opacity-50"
        >
          {reenriching ? 'Queuing…' : 'Re-enrich'}
        </button>
        {reenrichMsg && <span className="font-mono text-xs text-textdim">{reenrichMsg}</span>}
      </div>

      {/* Memory units */}
      <div>
        <h3 className="mb-2 font-sans text-sm font-semibold text-textdim">
          Recent memory units ({detail.recent_memory_units.length})
        </h3>
        <div className="flex flex-col gap-2">
          {detail.recent_memory_units.length === 0 && (
            <p className="font-sans text-xs text-textdim">None</p>
          )}
          {detail.recent_memory_units.map((u) => (
            <div key={u.unit_id} className="rounded-lg border border-border bg-surface p-3">
              <p className="font-sans text-sm text-text">{u.content_first_person}</p>
              <p className="mt-1 font-mono text-xs text-textdim">
                {u.memory_category} · fidelity {u.fidelity_score.toFixed(2)} ·{' '}
                {u.verified ? '✓ verified' : 'unverified'}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Relationships */}
      <div>
        <h3 className="mb-2 font-sans text-sm font-semibold text-textdim">
          Relationships ({detail.relationships.length})
        </h3>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full font-sans text-sm">
            <thead>
              <tr className="border-b border-border bg-surface">
                {['Email', 'Entity', 'Relationship', 'Address', ''].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-semibold text-textdim">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {detail.relationships.map((r) => (
                <tr key={r.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-text">{r.listener_email || r.listener_user_id}</td>
                  <td className="px-3 py-2 text-textdim">{r.entity_canonical}</td>
                  <td className="px-3 py-2 text-textdim">{r.relationship}</td>
                  <td className="px-3 py-2 text-textdim">{r.address_term || '—'}</td>
                  <td className="px-3 py-2">
                    <button
                      className="font-sans text-xs text-red-500 hover:underline"
                      onClick={() => handleRemoveRelationship(r.listener_user_id)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
              {detail.relationships.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center font-sans text-xs text-textdim">
                    No relationships
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <AddRelationshipForm personaId={personaId} onAdded={handleRelationshipAdded} />
      </div>
    </div>
  )
}

// ── AdminPage ─────────────────────────────────────────────────────────────────

export function AdminPage() {
  const { valid, checking, error, submit, setKey } = useAdminKey()
  const [keyInput, setKeyInput] = useState('')

  const [stats, setStats] = useState<AdminStats | null>(null)
  const [personas, setPersonas] = useState<AdminPersonaRow[]>([])
  const [loadErr, setLoadErr] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    if (!valid) return
    Promise.all([adminGetStats(), adminListPersonas()])
      .then(([s, p]) => {
        setStats(s)
        setPersonas(p)
      })
      .catch((e) => setLoadErr(e instanceof Error ? e.message : 'Failed to load'))
  }, [valid])

  if (!valid) {
    return (
      <KeyForm
        checking={checking}
        error={error}
        onSubmit={(k) => {
          setKeyInput(k)
          submit(k)
        }}
      />
    )
  }

  return (
    <div className="min-h-screen bg-bg p-8">
      <div className="mx-auto max-w-6xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <span className="font-fraunces text-2xl font-semibold text-text">EchoPersona Admin</span>
          <button
            className="font-sans text-xs text-textdim hover:text-text"
            onClick={() => {
              localStorage.removeItem('adminKey')
              setKey('')
              window.location.reload()
            }}
          >
            Sign out
          </button>
        </div>

        {loadErr && (
          <p className="mb-4 font-sans text-sm text-red-500">{loadErr}</p>
        )}

        {selectedId ? (
          <PersonaDetailPanel
            personaId={selectedId}
            onClose={() => setSelectedId(null)}
          />
        ) : (
          <div className="flex flex-col gap-6">
            {stats && <StatsBar stats={stats} />}
            <PersonaTable rows={personas} onSelect={setSelectedId} />
          </div>
        )}
      </div>
    </div>
  )
}
