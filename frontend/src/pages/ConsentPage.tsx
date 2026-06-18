import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getConsent, getPersona, getSuccession, saveConsent, saveSuccession } from '../lib/api'
import type { ConsentRecord, ConsentRights, ModalityConsent, Persona, SuccessionRecord } from '../types'

const DEFAULT_MODALITY: ModalityConsent = { text_twin: true, voice_clone: false, video_avatar: false }
const DEFAULT_RIGHTS: ConsentRights = { subject_may_review: true, subject_may_delete: true }

const inputCls =
  'w-full rounded-none border-0 border-b border-border bg-transparent px-0 py-2.5 font-sans text-sm text-text placeholder:text-muted outline-none transition-colors focus:border-blue'

function Spinner({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin text-green`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function CheckRow({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  hint?: string
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 py-2.5">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-[#18181B]"
      />
      <span>
        <span className="font-sans text-sm text-text">{label}</span>
        {hint && <span className="mt-0.5 block font-sans text-xs text-muted">{hint}</span>}
      </span>
    </label>
  )
}

export function ConsentPage() {
  const { personaId } = useParams<{ personaId: string }>()
  const navigate = useNavigate()

  // Page load
  const [persona, setPersona] = useState<Persona | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Consent form
  const [consentRecord, setConsentRecord] = useState<ConsentRecord | null>(null)
  const [hasConsent, setHasConsent] = useState(false)
  const [modality, setModality] = useState<ModalityConsent>(DEFAULT_MODALITY)
  const [rights, setRights] = useState<ConsentRights>(DEFAULT_RIGHTS)
  const [consentBusy, setConsentBusy] = useState(false)
  const [consentSaveError, setConsentSaveError] = useState<string | null>(null)
  const [consentSaved, setConsentSaved] = useState(false)

  // Succession form
  const [successionRecord, setSuccessionRecord] = useState<SuccessionRecord | null>(null)
  const [showSuccessionForm, setShowSuccessionForm] = useState(false)
  const [benefEmail, setBenefEmail] = useState('')
  const [benefRelationship, setBenefRelationship] = useState('')
  const [benefScope, setBenefScope] = useState<'full' | 'curated'>('full')
  const [benefTrigger, setBenefTrigger] = useState<'immediate' | 'posthumous_verified'>(
    'posthumous_verified',
  )
  const [succBusy, setSuccBusy] = useState(false)
  const [succSaveError, setSuccSaveError] = useState<string | null>(null)
  const [succSaved, setSuccSaved] = useState(false)

  useEffect(() => {
    if (!personaId) return
    Promise.all([getPersona(personaId), getConsent(personaId), getSuccession(personaId)])
      .then(([p, c, s]) => {
        setPersona(p)
        if (c) {
          setConsentRecord(c)
          setHasConsent(true)
          setModality(c.modality_consent)
          setRights(c.rights)
        }
        if (s && s.beneficiaries.length > 0) {
          setSuccessionRecord(s)
          const b = s.beneficiaries[0]
          setBenefEmail(b.user_id)
          setBenefRelationship(b.relationship)
          setBenefScope(b.scope)
          setBenefTrigger(b.activation_trigger)
          setShowSuccessionForm(true)
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [personaId])

  useEffect(() => {
    if (!consentSaved) return
    const t = setTimeout(() => setConsentSaved(false), 3000)
    return () => clearTimeout(t)
  }, [consentSaved])

  useEffect(() => {
    if (!succSaved) return
    const t = setTimeout(() => setSuccSaved(false), 3000)
    return () => clearTimeout(t)
  }, [succSaved])

  async function handleSaveConsent() {
    if (!personaId) return
    setConsentBusy(true)
    setConsentSaveError(null)
    try {
      const record = await saveConsent(personaId, { modality_consent: modality, rights })
      setConsentRecord(record)
      setHasConsent(true)
      setConsentSaved(true)
    } catch (e) {
      setConsentSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setConsentBusy(false)
    }
  }

  async function handleSaveSuccession() {
    if (!personaId) return
    const userId = benefEmail.trim()
    const relationship = benefRelationship.trim()
    if (!userId || !relationship) {
      setSuccSaveError('Email and relationship are required.')
      return
    }
    setSuccBusy(true)
    setSuccSaveError(null)
    try {
      const record = await saveSuccession(personaId, {
        beneficiaries: [{ user_id: userId, relationship, scope: benefScope, activation_trigger: benefTrigger }],
      })
      setSuccessionRecord(record)
      setSuccSaved(true)
    } catch (e) {
      setSuccSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSuccBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="flex items-center gap-3">
          <Spinner />
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
      {/* Header bar */}
      <div className="border-b border-border bg-surface px-6 py-3 shadow-card lg:px-10">
        <div className="mx-auto flex max-w-[1440px] items-center gap-4">
          <button
            className="font-sans text-sm text-muted transition-colors hover:text-text"
            onClick={() => navigate(`/dashboard/persona/${personaId}`)}
          >
            ← {persona.name}
          </button>
          <span className="text-border">|</span>
          <span className="font-sans text-sm text-textdim">Consent & Succession</span>
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-[640px] px-6 py-10 lg:px-0">
        <div className="mb-8">
          <h1 className="font-fraunces text-2xl font-semibold text-text">Consent & Succession</h1>
          <p className="mt-1 font-sans text-sm text-textdim">
            Choose how your twin can be used and who may access it after you.
          </p>
          {!hasConsent && (
            <p className="mt-2 font-sans text-xs text-muted">No consent saved yet — defaults shown.</p>
          )}
          {hasConsent && consentRecord && (
            <p className="mt-2 font-sans text-xs text-muted">
              Last saved {new Date(consentRecord.captured_at).toLocaleString()} · version{' '}
              {consentRecord.consent_version}
            </p>
          )}
        </div>

        <div className="space-y-5">
          {/* Modalities */}
          <div className="rounded-2xl border border-border bg-surface px-6 py-5 shadow-card">
            <p className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-muted">
              Allowed modalities
            </p>
            <div className="mt-3 divide-y divide-border">
              <CheckRow
                checked={modality.text_twin}
                onChange={(v) => setModality((m) => ({ ...m, text_twin: v }))}
                label="Text twin"
                hint="Allow this persona to respond in text-based conversations."
              />
              <CheckRow
                checked={modality.voice_clone}
                onChange={(v) => setModality((m) => ({ ...m, voice_clone: v }))}
                label="Voice clone"
                hint="Allow this persona to speak in a cloned voice."
              />
              <CheckRow
                checked={modality.video_avatar}
                onChange={(v) => setModality((m) => ({ ...m, video_avatar: v }))}
                label="Video avatar"
                hint="Allow this persona to appear as an animated video avatar."
              />
            </div>
          </div>

          {/* Rights */}
          <div className="rounded-2xl border border-border bg-surface px-6 py-5 shadow-card">
            <p className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-muted">
              Your rights
            </p>
            <div className="mt-3 divide-y divide-border">
              <CheckRow
                checked={rights.subject_may_review}
                onChange={(v) => setRights((r) => ({ ...r, subject_may_review: v }))}
                label="I can review my captured stories and answers"
                hint="You may view all stories and answers captured for this persona."
              />
              <CheckRow
                checked={rights.subject_may_delete}
                onChange={(v) => setRights((r) => ({ ...r, subject_may_delete: v }))}
                label="I can request deletion of my data"
                hint="You may submit a deletion request and have your data removed."
              />
            </div>
          </div>

          {/* Consent save row */}
          <div className="flex items-center gap-4">
            <button
              onClick={handleSaveConsent}
              disabled={consentBusy}
              className="rounded-lg bg-accent px-5 py-2.5 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {consentBusy ? (
                <span className="flex items-center gap-2">
                  <Spinner className="h-4 w-4" />
                  Saving…
                </span>
              ) : (
                'Save consent'
              )}
            </button>
            {consentSaved && <span className="font-sans text-sm text-green">Saved ✓</span>}
            {consentSaveError && <span className="font-sans text-sm text-red">{consentSaveError}</span>}
          </div>

          {/* Succession */}
          <div className="rounded-2xl border border-border bg-surface px-6 py-5 shadow-card">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-muted">
                  Succession intent
                </p>
                <p className="mt-0.5 font-sans text-xs text-muted">
                  Optional — who may access this twin after you.
                </p>
              </div>
              {!showSuccessionForm && !successionRecord && (
                <button
                  onClick={() => setShowSuccessionForm(true)}
                  className="font-sans text-xs text-green transition-opacity hover:opacity-70"
                >
                  + Add beneficiary
                </button>
              )}
            </div>

            {!showSuccessionForm && !successionRecord && (
              <p className="mt-3 font-sans text-sm text-textdim">
                Designate a trusted person to access this twin on your behalf.
              </p>
            )}

            {/* Saved summary when form is hidden */}
            {!showSuccessionForm && successionRecord && successionRecord.beneficiaries.length > 0 && (
              <div className="mt-3 flex items-center justify-between rounded-lg border border-border bg-elevated px-3 py-2">
                <div>
                  <span className="font-sans text-sm text-text">
                    {successionRecord.beneficiaries[0].relationship}
                  </span>
                  <span className="ml-2 font-sans text-xs text-muted">
                    {successionRecord.beneficiaries[0].user_id}
                  </span>
                  <span className="ml-2 font-sans text-xs text-muted">
                    · {successionRecord.beneficiaries[0].scope === 'full' ? 'Full access' : 'Curated'}
                  </span>
                  <span className="ml-1 font-sans text-xs text-muted">
                    · {successionRecord.beneficiaries[0].activation_trigger === 'immediate' ? 'Immediately' : 'After verified passing'}
                  </span>
                </div>
                <button
                  onClick={() => setShowSuccessionForm(true)}
                  className="font-sans text-xs text-muted hover:text-textdim"
                >
                  Edit
                </button>
              </div>
            )}

            {showSuccessionForm && (
              <div className="mt-5 space-y-5">
                {/* Email */}
                <div>
                  <label className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-muted">
                    Beneficiary email
                  </label>
                  <input
                    type="email"
                    value={benefEmail}
                    onChange={(e) => setBenefEmail(e.target.value)}
                    placeholder="their@email.com"
                    className={inputCls}
                  />
                  <p className="mt-1 font-sans text-xs text-muted">
                    Must be their EchoPersona account email.
                  </p>
                </div>

                {/* Relationship */}
                <div>
                  <label className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-muted">
                    Relationship
                  </label>
                  <input
                    type="text"
                    value={benefRelationship}
                    onChange={(e) => setBenefRelationship(e.target.value)}
                    placeholder="e.g. spouse, child, close friend"
                    className={inputCls}
                  />
                </div>

                {/* Scope */}
                <div>
                  <p className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-muted">
                    Access scope
                  </p>
                  <div className="mt-2 flex gap-2">
                    {(['full', 'curated'] as const).map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => setBenefScope(s)}
                        className={`rounded-lg px-3 py-1.5 font-sans text-xs font-medium transition-colors ${
                          benefScope === s
                            ? 'bg-accent text-white'
                            : 'border border-border text-textdim hover:text-text'
                        }`}
                      >
                        {s === 'full' ? 'Full access' : 'Curated'}
                      </button>
                    ))}
                  </div>
                  <p className="mt-1.5 font-sans text-xs text-muted">
                    {benefScope === 'full'
                      ? 'Beneficiary can access all conversations and memories.'
                      : 'Beneficiary can only access memories you have marked as shareable.'}
                  </p>
                </div>

                {/* Activation trigger */}
                <div>
                  <p className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-muted">
                    When activated
                  </p>
                  <div className="mt-2 flex gap-2">
                    {(['immediate', 'posthumous_verified'] as const).map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setBenefTrigger(t)}
                        className={`rounded-lg px-3 py-1.5 font-sans text-xs font-medium transition-colors ${
                          benefTrigger === t
                            ? 'bg-accent text-white'
                            : 'border border-border text-textdim hover:text-text'
                        }`}
                      >
                        {t === 'immediate' ? 'Immediately' : 'After verified passing'}
                      </button>
                    ))}
                  </div>
                  <p className="mt-1.5 font-sans text-xs text-muted">
                    {benefTrigger === 'immediate'
                      ? 'Access is granted as soon as the beneficiary accepts.'
                      : 'Access is granted only after a passing has been confirmed by the platform.'}
                  </p>
                </div>

                {/* Succession save row */}
                <div className="flex items-center gap-4 pt-1">
                  <button
                    onClick={handleSaveSuccession}
                    disabled={succBusy}
                    className="rounded-lg bg-accent px-5 py-2.5 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {succBusy ? (
                      <span className="flex items-center gap-2">
                        <Spinner className="h-4 w-4" />
                        Saving…
                      </span>
                    ) : (
                      'Save succession intent'
                    )}
                  </button>
                  <button
                    onClick={() => setShowSuccessionForm(false)}
                    className="font-sans text-sm text-muted hover:text-textdim"
                  >
                    Cancel
                  </button>
                  {succSaved && <span className="font-sans text-sm text-green">Saved ✓</span>}
                  {succSaveError && <span className="font-sans text-sm text-red">{succSaveError}</span>}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
