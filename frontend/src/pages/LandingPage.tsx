import { useNavigate } from 'react-router-dom'

export function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-bg text-text">
      {/* Nav */}
      <nav className="flex items-center justify-between border-b border-border bg-surface px-8 py-4 shadow-card">
        <span className="font-fraunces text-xl font-semibold text-text">
          EchoPersona
        </span>
        <div className="flex items-center gap-4">
          <button
            className="font-sans text-sm text-textdim transition-colors hover:text-text"
            onClick={() => navigate('/login')}
          >
            Login
          </button>
          <button
            className="rounded-lg bg-accent px-4 py-2 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
            onClick={() => navigate('/signup')}
          >
            Get Started
          </button>
        </div>
      </nav>

      {/* Hero */}
      <section className="mx-auto max-w-4xl px-8 py-24 text-center">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-border bg-elevated px-4 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-green" />
          <span className="font-sans text-[11px] text-textdim">
            Sub-600ms response — feels like a real conversation
          </span>
        </div>
        <h1 className="mt-6 font-fraunces text-5xl font-semibold leading-tight tracking-tight text-text">
          Talk to the people<br />you love.{' '}
          <span className="text-green">Forever.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl font-sans text-lg text-textdim">
          Real-time AI personas built from memories, stories, and voice.
          Sub-second latency that makes every conversation feel present.
        </p>
        <div className="mt-10 flex items-center justify-center gap-4">
          <button
            className="rounded-lg bg-accent px-8 py-3.5 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
            onClick={() => navigate('/signup')}
          >
            Create Your Legacy →
          </button>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-border bg-surface py-12 shadow-card">
        <div className="mx-auto flex max-w-3xl justify-around px-8">
          {[
            { value: '<600ms', label: 'Response latency' },
            { value: '50+',    label: 'Concurrent users' },
            { value: '2 min',  label: 'Voice cloning' },
          ].map(({ value, label }) => (
            <div key={label} className="text-center">
              <p className="font-mono text-3xl font-bold text-text">{value}</p>
              <p className="mt-1 font-sans text-sm text-textdim">{label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section className="mx-auto max-w-4xl px-8 py-20">
        <h2 className="mb-12 text-center font-fraunces text-2xl font-semibold text-text">
          How It Works
        </h2>
        <div className="grid gap-6 md:grid-cols-3">
          {[
            {
              step: '01',
              title: 'Upload Stories',
              desc: 'Share memories, personality traits, and speaking style to define the persona.',
            },
            {
              step: '02',
              title: 'Clone Voice',
              desc: '30 seconds of audio is all it takes to recreate a unique voice.',
            },
            {
              step: '03',
              title: 'Start Talking',
              desc: 'Real-time voice conversation with sub-600ms latency, in their voice.',
            },
          ].map(({ step, title, desc }) => (
            <div key={step} className="card-hover rounded-xl border border-border bg-surface p-6 shadow-card">
              <p className="font-mono text-xs text-muted">{step}</p>
              <h3 className="mt-3 font-fraunces text-lg font-semibold text-text">{title}</h3>
              <p className="mt-2 font-sans text-sm leading-relaxed text-textdim">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border bg-elevated py-20 text-center">
        <h2 className="font-fraunces text-3xl font-semibold text-text">
          Preserve someone's voice today.
        </h2>
        <button
          className="mt-8 rounded-lg bg-accent px-10 py-4 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
          onClick={() => navigate('/signup')}
        >
          Get Started Free →
        </button>
      </section>

      {/* Footer */}
      <footer className="border-t border-border bg-surface px-8 py-6 text-center">
        <p className="font-sans text-xs text-muted">
          © 2026 EchoPersona. Built with care.
        </p>
      </footer>
    </div>
  )
}
