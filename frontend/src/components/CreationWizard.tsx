import { useCallback, useEffect, useState } from 'react'
import { captureTextAnswer, finishCreationSession, startCreationSession } from '../lib/api'
import type { CreationSession } from '../types'

interface CreationWizardProps {
  personaId: string
  onComplete: (personaId: string) => void
}

const TOTAL_QUESTIONS = 41
const MIN_QUESTIONS_TO_FINISH = 10

const CATEGORY_LABELS: Record<string, string> = {
  origins: 'Origins',
  family: 'Family',
  coming_of_age: 'Coming of Age',
  love: 'Love',
  work: 'Work',
  beliefs: 'Beliefs & Values',
  texture: 'Your Voice',
  hardship: 'Hardship',
  places: 'Places',
  legacy: 'Legacy',
  _consent: 'Consent',
}

export function CreationWizard({ personaId, onComplete }: CreationWizardProps) {
  const [session, setSession] = useState<CreationSession | null>(null)
  const [currentPrompt, setCurrentPrompt] = useState('')
  const [currentCategory, setCurrentCategory] = useState<string | null>(null)
  const [steerHint, setSteerHint] = useState<string | null>(null)
  const [answerText, setAnswerText] = useState('')
  const [answeredCount, setAnsweredCount] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isFinishing, setIsFinishing] = useState(false)
  const [isDone, setIsDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadSession = useCallback(() => {
    setIsLoading(true)
    setError(null)
    startCreationSession(personaId)
      .then(({ session: s, next_step }) => {
        setSession(s)
        setCurrentPrompt(next_step.question_prompt ?? next_step.prompt ?? '')
        setCurrentCategory(next_step.question_category ?? null)
        setAnsweredCount(s.completed_question_ids.length)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Something went wrong'))
      .finally(() => setIsLoading(false))
  }, [personaId])

  useEffect(() => { loadSession() }, [loadSession])

  const handleSubmit = async () => {
    if (!session || !answerText.trim() || isSubmitting) return
    setIsSubmitting(true)
    setError(null)
    try {
      const { next_step } = await captureTextAnswer(session.session_id, answerText.trim())
      const { action, prompt, question_prompt, question_category, session: updated } = next_step
      setSession(updated)
      setAnsweredCount(updated.completed_question_ids.length)
      setAnswerText('')
      setSteerHint(null)
      if (action === 'ask_probe') {
        setCurrentPrompt(prompt ?? '')
        setCurrentCategory(question_category ?? null)
      } else if (action === 'advance') {
        setCurrentPrompt(question_prompt ?? '')
        setCurrentCategory(question_category ?? null)
      } else if (action === 'steer') {
        setSteerHint(prompt)
      } else if (action === 'done') {
        setIsDone(true)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleFinish = async () => {
    if (!session || isFinishing) return
    setIsFinishing(true)
    setError(null)
    try {
      await finishCreationSession(session.session_id)
      onComplete(personaId)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to finish')
      setIsFinishing(false)
    }
  }

  const canFinish = answeredCount >= MIN_QUESTIONS_TO_FINISH || isDone
  const categoryLabel = currentCategory ? (CATEGORY_LABELS[currentCategory] ?? currentCategory) : null
  const categoryCount: number = (currentCategory ? (session?.answers_per_category[currentCategory] ?? 0) : 0)

  // ── Loading state ──────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-surface py-16 text-center shadow-card">
        <svg className="mb-4 h-6 w-6 animate-spin text-accent" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="font-sans text-sm text-textdim">Preparing your questions…</span>
      </div>
    )
  }

  // ── Error state — session failed to load ───────────────────────────────
  if (!session) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-surface py-16 text-center shadow-card">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-cream">
          <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6 text-textdim">
            <path d="M12 9v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <p className="mb-1 font-fraunces text-lg font-semibold text-text">
          We had trouble getting started
        </p>
        <p className="mb-6 max-w-sm font-sans text-sm text-textdim">
          {error || 'Something went wrong loading the interview. Please try again.'}
        </p>
        <button
          className="rounded-lg bg-accent px-6 py-2.5 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
          onClick={loadSession}
        >
          Try again
        </button>
      </div>
    )
  }

  // ── Interview UI ───────────────────────────────────────────────────────
  const progressPercent = Math.min(100, (answeredCount / TOTAL_QUESTIONS) * 100)

  return (
    <div className="rounded-2xl border border-border bg-surface shadow-card">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-6 py-4 sm:px-8">
        <div className="flex items-center gap-3">
          {categoryLabel && (
            <span className="rounded-full bg-cream px-3 py-1 font-sans text-xs font-semibold text-accent">
              {categoryLabel}
            </span>
          )}
          {categoryLabel && categoryCount > 0 && (
            <span className="font-sans text-xs text-muted">
              {categoryCount} answered
            </span>
          )}
        </div>
        <span className="font-sans text-xs text-muted">
          {answeredCount === 0
            ? `${TOTAL_QUESTIONS} questions to explore`
            : answeredCount < MIN_QUESTIONS_TO_FINISH
              ? `${answeredCount} answered — ${MIN_QUESTIONS_TO_FINISH - answeredCount} more to unlock finish`
              : `${answeredCount} of ${TOTAL_QUESTIONS} answered`}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 w-full bg-elevated">
        <div
          className="h-1.5 bg-accent transition-all duration-500 ease-out"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Question + answer area */}
      <div className="px-6 py-8 sm:px-8">
        {steerHint && (
          <p className="mb-4 rounded-lg bg-cream/60 px-4 py-3 font-sans text-sm italic text-textdim">
            {steerHint}
          </p>
        )}

        <p className="mb-6 font-fraunces text-xl font-semibold leading-relaxed text-text sm:text-2xl">
          {currentPrompt}
        </p>

        <textarea
          className="w-full resize-none rounded-xl border border-border bg-bg p-4 font-sans text-sm leading-relaxed text-text placeholder:text-muted focus:border-accent/30 focus:outline-none focus:ring-2 focus:ring-accent/20"
          rows={5}
          placeholder="Take your time — there are no wrong answers…"
          value={answerText}
          onChange={(e) => setAnswerText(e.target.value)}
          disabled={isSubmitting || isDone}
          autoFocus
        />

        {error && (
          <div className="mt-3 flex items-start gap-2 rounded-lg bg-red/5 px-4 py-3">
            <svg viewBox="0 0 20 20" fill="currentColor" className="mt-0.5 h-4 w-4 shrink-0 text-red">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <p className="font-sans text-sm text-red">{error}</p>
          </div>
        )}

        <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
          {!isDone && (
            <button
              className="rounded-lg bg-accent px-6 py-3 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              onClick={handleSubmit}
              disabled={!answerText.trim() || isSubmitting}
            >
              {isSubmitting ? 'Saving…' : 'Continue →'}
            </button>
          )}

          {canFinish && (
            <button
              className="rounded-lg border border-green bg-green/5 px-6 py-3 font-sans text-sm font-medium text-green transition-colors hover:bg-green/10 disabled:opacity-40"
              onClick={handleFinish}
              disabled={isFinishing}
            >
              {isFinishing ? 'Finishing…' : 'Finish & build persona'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
