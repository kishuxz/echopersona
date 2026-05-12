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
    'w-full rounded border border-border bg-bg px-3 py-2.5 font-sans text-sm text-text placeholder:text-muted outline-none transition-colors focus:border-green'
  const labelCls = 'block font-mono text-[10px] uppercase tracking-widest text-textdim mb-1.5'

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
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="font-mono text-2xl font-bold uppercase tracking-[0.15em] text-green">
            EchoPersona
          </h1>
          <p className="mt-1 font-sans text-sm text-textdim">
            {mode === 'login' ? 'Sign in to your account' : 'Create an account'}
          </p>
        </div>

        {confirmMessage ? (
          <div className="rounded-lg border border-green/30 bg-surface p-6 text-center">
            <p className="font-mono text-sm text-green">{confirmMessage}</p>
            <button
              className="mt-4 font-mono text-xs text-textdim underline"
              onClick={() => { setConfirmMessage(null); setMode('login') }}
            >
              Back to login
            </button>
          </div>
        ) : (
          <div className="rounded-lg border border-border bg-surface p-6">
            <div className="mb-6 flex rounded border border-border">
              <button
                className={`flex-1 py-2 font-mono text-xs uppercase tracking-widest transition-colors ${
                  mode === 'login' ? 'bg-green text-bg' : 'text-textdim hover:text-text'
                }`}
                onClick={() => { setMode('login'); setError(null) }}
              >
                Login
              </button>
              <button
                className={`flex-1 py-2 font-mono text-xs uppercase tracking-widest transition-colors ${
                  mode === 'signup' ? 'bg-green text-bg' : 'text-textdim hover:text-text'
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
                <p className="font-mono text-[10px] text-red-400">{error}</p>
              )}

              <button
                type="submit"
                disabled={loading}
                className="mt-1 w-full rounded py-3 font-mono text-sm font-bold uppercase tracking-widest transition-all disabled:opacity-40"
                style={
                  loading
                    ? { background: '#111', border: '1px solid #00ff88', color: '#00ff88' }
                    : { background: '#00ff88', color: '#00170c' }
                }
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="#00ff88" strokeWidth="3" />
                      <path className="opacity-80" fill="#00ff88" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
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
