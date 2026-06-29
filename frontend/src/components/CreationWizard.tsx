import { useEffect, useState } from 'react'
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

  useEffect(() => {
    startCreationSession(personaId)
      .then(({ session: s, next_step }) => {
        setSession(s)
        setCurrentPrompt(next_step.question_prompt ?? next_step.prompt ?? '')
        setCurrentCategory(next_step.question_category ?? null)
        setAnsweredCount(s.completed_question_ids.length)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to start interview'))
      .finally(() => setIsLoading(false))
  }, [personaId])

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

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8">
        <svg className="h-4 w-4 animate-spin text-accent" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="font-sans text-sm text-textdim">Starting interview…</span>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-6 shadow-card">
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-sans text-xs font-medium uppercase tracking-widest text-muted">
            Building your persona
          </span>
          {categoryLabel && (
            <>
              <span className="text-xs text-muted">·</span>
              <span className="font-sans text-xs font-semibold text-accent">
                {categoryLabel}
              </span>
              {categoryCount > 0 && (
                <span className="font-sans text-xs text-muted">
                  {categoryCount} answered
                </span>
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="font-sans text-xs text-muted">
            {answeredCount} of {TOTAL_QUESTIONS}
          </span>
          {!isDone && answeredCount < MIN_QUESTIONS_TO_FINISH && (
            <span className="font-sans text-xs text-muted">
              ({MIN_QUESTIONS_TO_FINISH - answeredCount} more to unlock finish)
            </span>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-5 h-1 w-full rounded-full bg-border">
        <div
          className="h-1 rounded-full bg-accent transition-all duration-300"
          style={{ width: `${Math.min(100, (answeredCount / TOTAL_QUESTIONS) * 100)}%` }}
        />
      </div>

      {steerHint && (
        <p className="mb-3 font-sans text-sm italic text-textdim">{steerHint}</p>
      )}

      <p className="mb-4 font-fraunces text-base font-semibold leading-relaxed text-text">
        {currentPrompt}
      </p>

      <textarea
        className="w-full resize-none rounded-lg border border-border bg-bg p-3 font-sans text-sm text-text placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/30"
        rows={4}
        placeholder="Type your answer here…"
        value={answerText}
        onChange={(e) => setAnswerText(e.target.value)}
        disabled={isSubmitting || isDone}
      />

      {error && (
        <p className="mt-2 font-sans text-xs text-red">{error}</p>
      )}

      <div className="mt-4 flex flex-col gap-3">
        {!isDone && (
          <button
            className="rounded-lg bg-accent px-5 py-2.5 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            onClick={handleSubmit}
            disabled={!answerText.trim() || isSubmitting}
          >
            {isSubmitting ? 'Saving…' : 'Continue →'}
          </button>
        )}

        {canFinish && (
          <button
            className="rounded-lg border border-green bg-green/10 px-5 py-2.5 font-sans text-sm font-medium text-green transition-colors hover:bg-green/20 disabled:opacity-40"
            onClick={handleFinish}
            disabled={isFinishing}
          >
            {isFinishing ? 'Finishing…' : 'Finish building persona'}
          </button>
        )}
      </div>
    </div>
  )
}
