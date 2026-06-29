import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getBillingStatus, startCheckout } from '../lib/api'
import type { BillingStatus } from '../types'

function Spinner({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin text-green`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

const TIER_LABEL: Record<BillingStatus['plan_tier'], string> = {
  free: 'Free',
  creator: 'Creator',
  legacy: 'Legacy',
  preservation: 'Preservation',
}

const TIER_PILL: Record<BillingStatus['plan_tier'], string> = {
  free: 'bg-cream text-textdim',
  creator: 'bg-green/10 text-green',
  legacy: 'bg-accent text-white',
  preservation: 'bg-amber-100 text-amber-800',
}

const TIER_ORDER: Record<BillingStatus['plan_tier'], number> = {
  free: 0,
  creator: 1,
  legacy: 2,
  preservation: 3,
}

const STATUS_LABEL: Record<NonNullable<BillingStatus['status']>, string> = {
  active: 'Active',
  trialing: 'Trial',
  past_due: 'Payment past due',
  canceled: 'Canceled',
  unpaid: 'Unpaid',
}

const STATUS_CLASS: Record<NonNullable<BillingStatus['status']>, string> = {
  active: 'text-green',
  trialing: 'text-textdim',
  past_due: 'text-red',
  canceled: 'text-textdim',
  unpaid: 'text-red',
}

export function BillingPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<BillingStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  const [checkoutBusy, setCheckoutBusy] = useState<'creator' | 'legacy' | 'preservation' | null>(null)

  useEffect(() => {
    getBillingStatus()
      .then(setStatus)
      .catch((e) => setLoadError(e.message))
      .finally(() => setLoading(false))
  }, [])

  async function handleUpgrade(tier: 'creator' | 'legacy') {
    setCheckoutBusy(tier)
    setCheckoutError(null)
    try {
      await startCheckout(tier)
    } catch (e) {
      setCheckoutError(
        e instanceof Error ? e.message : 'Could not start checkout. Please try again.',
      )
    } finally {
      setCheckoutBusy(null)
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

  if (loadError || !status) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="text-center">
          <p className="font-sans text-sm text-red">{loadError ?? 'Could not load billing status.'}</p>
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

  const currentOrder = TIER_ORDER[status.plan_tier]
  const showCreator = currentOrder < TIER_ORDER['creator']
  const showLegacy = currentOrder < TIER_ORDER['legacy']
  const showPreservationCta = !status.is_preservation_locked && status.plan_tier !== 'preservation'

  const periodEnd = status.current_period_end
    ? new Date(status.current_period_end).toLocaleDateString()
    : null

  const familyLimitLabel =
    status.family_member_limit === null
      ? 'Unlimited family members'
      : status.family_member_limit === 0
      ? 'No family access'
      : `Up to ${status.family_member_limit} family member${status.family_member_limit === 1 ? '' : 's'}`

  return (
    <div className="min-h-screen bg-bg text-text">
      {/* Header */}
      <div className="border-b border-border bg-surface px-6 py-3 shadow-card lg:px-10">
        <div className="mx-auto flex max-w-[1440px] items-center gap-4">
          <button
            className="font-sans text-sm text-muted transition-colors hover:text-text"
            onClick={() => navigate('/dashboard')}
          >
            ← Dashboard
          </button>
          <span className="text-border">|</span>
          <span className="font-sans text-sm text-textdim">Billing & Plan</span>
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-xl px-6 py-10 lg:px-0">
        {/* Status card */}
        <div className="rounded-2xl border border-border bg-surface px-6 py-5 shadow-card">
          <h2 className="mb-4 font-fraunces text-lg font-semibold text-text">Current plan</h2>

          {/* Plan tier */}
          <div className="mb-4 flex items-center gap-3 flex-wrap">
            <span className={`rounded-full px-3 py-1 font-sans text-xs font-medium ${TIER_PILL[status.plan_tier]}`}>
              {TIER_LABEL[status.plan_tier]}
            </span>
            {status.status && (
              <span className={`font-sans text-sm ${STATUS_CLASS[status.status]}`}>
                {STATUS_LABEL[status.status]}
              </span>
            )}
            {status.is_preservation_locked && (
              <span className="rounded-full bg-amber-100 px-2.5 py-0.5 font-sans text-[10px] text-amber-800">
                Preserved
              </span>
            )}
          </div>

          {/* Feature access */}
          <div className="mb-3 flex items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-0.5 font-sans text-[10px] ${
                status.can_use_chat ? 'bg-green/10 text-green' : 'bg-cream text-textdim'
              }`}
            >
              Chat
            </span>
            <span
              className={`rounded-full px-2.5 py-0.5 font-sans text-[10px] ${
                status.can_use_voice ? 'bg-green/10 text-green' : 'bg-cream text-textdim'
              }`}
            >
              Voice
            </span>
            <span
              className={`rounded-full px-2.5 py-0.5 font-sans text-[10px] ${
                status.can_use_video ? 'bg-green/10 text-green' : 'bg-cream text-textdim'
              }`}
            >
              Video
            </span>
          </div>

          {/* Family member limit */}
          <p className="mb-3 font-sans text-xs text-textdim">{familyLimitLabel}</p>

          {/* Period info */}
          {periodEnd && !status.cancel_at_period_end && (
            <p className="font-sans text-xs text-textdim">Renews {periodEnd}</p>
          )}
          {periodEnd && status.cancel_at_period_end && (
            <p className="font-sans text-xs text-textdim">Cancels on {periodEnd}</p>
          )}
        </div>

        {/* Subscription upgrade buttons */}
        {(showCreator || showLegacy) && (
          <div className="mt-6">
            <h3 className="mb-3 font-sans text-sm font-medium text-textdim">Upgrade your plan</h3>
            <div className="flex flex-col gap-3">
              {showCreator && (
                <button
                  className="flex items-center justify-center gap-2 rounded-lg bg-accent px-5 py-2.5 font-sans text-sm font-medium text-white disabled:opacity-60"
                  disabled={checkoutBusy !== null}
                  onClick={() => handleUpgrade('creator')}
                >
                  {checkoutBusy === 'creator' ? (
                    <>
                      <Spinner className="h-4 w-4" />
                      Redirecting…
                    </>
                  ) : (
                    'Upgrade to Creator'
                  )}
                </button>
              )}
              {showLegacy && (
                <button
                  className="flex items-center justify-center gap-2 rounded-lg bg-accent px-5 py-2.5 font-sans text-sm font-medium text-white disabled:opacity-60"
                  disabled={checkoutBusy !== null}
                  onClick={() => handleUpgrade('legacy')}
                >
                  {checkoutBusy === 'legacy' ? (
                    <>
                      <Spinner className="h-4 w-4" />
                      Redirecting…
                    </>
                  ) : (
                    'Upgrade to Legacy'
                  )}
                </button>
              )}
            </div>
            {checkoutError && (
              <p className="mt-3 font-sans text-sm text-red">{checkoutError}</p>
            )}
          </div>
        )}

        {/* Preservation CTA — one-time purchase, per-persona */}
        {showPreservationCta && (
          <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 px-6 py-5">
            <h3 className="mb-1 font-fraunces text-base font-semibold text-amber-900">
              Preservation
            </h3>
            <p className="mb-4 font-sans text-sm text-amber-800">
              One-time purchase that permanently locks your persona's memories — they're never
              deleted, even after you're gone. Family access continues as long as they keep an
              active plan.
            </p>
            <button
              className="rounded-lg border border-amber-400 bg-amber-100 px-4 py-2 font-sans text-sm font-medium text-amber-900 opacity-60 cursor-not-allowed"
              disabled
              title="Select a persona from your dashboard to purchase Preservation"
            >
              Purchase Preservation — select a persona first
            </button>
            <p className="mt-2 font-sans text-[11px] text-amber-700">
              Go to a persona's page to lock it permanently.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
