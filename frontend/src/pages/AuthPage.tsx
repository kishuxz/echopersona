import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

interface AuthPageProps {
  mode: 'login' | 'signup'
}

export function AuthPage({ mode: initialMode }: AuthPageProps) {
  const [mode, setMode] = useState(initialMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmMessage, setConfirmMessage] = useState<string | null>(null)

  const { signIn, signUp } = useAuth()
  const navigate = useNavigate()

  const inputCls =
    'w-full rounded-lg border border-border bg-surface px-3 py-2.5 font-sans text-sm text-text placeholder:text-muted outline-none transition-colors focus:border-blue focus:ring-2 focus:ring-blue/10'
  const labelCls = 'block font-sans text-[11px] font-medium uppercase tracking-widest text-muted mb-1.5'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      if (mode === 'login') {
        await signIn(email, password)
        navigate('/dashboard')
      } else {
        await signUp(email, password, fullName)
        setConfirmMessage('Check your email to confirm your account.')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-elevated px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="font-fraunces text-2xl font-semibold text-text">
            EchoPersona
          </h1>
          <p className="mt-1 font-sans text-sm text-textdim">
            {mode === 'login' ? 'Sign in to your account' : 'Create an account'}
          </p>
        </div>

        {confirmMessage ? (
          <div className="rounded-xl border border-border bg-surface p-6 text-center shadow-panel">
            <p className="font-sans text-sm text-green">{confirmMessage}</p>
            <button
              className="mt-4 font-sans text-sm text-textdim underline"
              onClick={() => { setConfirmMessage(null); setMode('login') }}
            >
              Back to login
            </button>
          </div>
        ) : (
          <div className="rounded-xl border border-border bg-surface p-6 shadow-panel">
            <div className="mb-6 flex rounded-lg border border-border overflow-hidden">
              <button
                className={`flex-1 py-2 font-sans text-sm font-medium transition-colors ${
                  mode === 'login' ? 'bg-accent text-white' : 'text-textdim hover:text-text'
                }`}
                onClick={() => { setMode('login'); setError(null) }}
              >
                Login
              </button>
              <button
                className={`flex-1 py-2 font-sans text-sm font-medium transition-colors ${
                  mode === 'signup' ? 'bg-accent text-white' : 'text-textdim hover:text-text'
                }`}
                onClick={() => { setMode('signup'); setError(null) }}
              >
                Sign Up
              </button>
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              {mode === 'signup' && (
                <div>
                  <label className={labelCls}>Full Name</label>
                  <input
                    type="text"
                    className={inputCls}
                    placeholder="Your name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    required
                  />
                </div>
              )}

              <div>
                <label className={labelCls}>Email</label>
                <input
                  type="email"
                  className={inputCls}
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>

              <div>
                <label className={labelCls}>Password</label>
                <input
                  type="password"
                  className={inputCls}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                />
              </div>

              {error && (
                <p className="font-sans text-sm text-red">{error}</p>
              )}

              <button
                type="submit"
                disabled={loading}
                className="mt-1 w-full rounded-lg py-3 font-sans text-sm font-medium text-white transition-opacity disabled:opacity-40"
                style={{ background: loading ? '#52525B' : '#18181B' }}
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                      <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    {mode === 'login' ? 'Signing in…' : 'Creating account…'}
                  </span>
                ) : mode === 'login' ? (
                  'Sign In'
                ) : (
                  'Create Account'
                )}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  )
}
