import { useNavigate } from 'react-router-dom'

export function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-bg text-text">
      {/* Nav */}
      <nav className="flex items-center justify-between border-b border-border px-8 py-4">
        <span className="font-mono text-lg font-bold uppercase tracking-[0.15em] text-green">
          EchoPersona
        </span>
        <div className="flex items-center gap-4">
          <button
            className="font-mono text-xs text-textdim transition-colors hover:text-text"
            onClick={() => navigate('/login')}
          >
            Login
          </button>
          <button
            className="rounded bg-green px-4 py-2 font-mono text-xs font-bold uppercase tracking-widest text-bg transition-opacity hover:opacity-90"
            onClick={() => navigate('/signup')}
          >
            Get Started
          </button>
        </div>
      </nav>

      {/* Hero */}
      <section className="mx-auto max-w-4xl px-8 py-24 text-center">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-green/20 bg-green/5 px-4 py-1">
          <span className="h-1.5 w-1.5 rounded-full bg-green" />
          <span className="font-mono text-[10px] uppercase tracking-widest text-green">
            ⚡ Sub-600ms response — feels like a real conversation
          </span>
        </div>
        <h1 className="mt-6 font-sans text-5xl font-bold leading-tight tracking-tight text-text">
          Talk to the people<br />you love.{' '}
          <span className="text-green">Forever.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl font-sans text-lg text-textdim">
          Real-time AI personas built from memories, stories, and voice.
          Sub-second latency that makes every conversation feel present.
        </p>
        <div className="mt-10 flex items-center justify-center gap-4">
          <button
            className="rounded bg-green px-8 py-3 font-mono text-sm font-bold uppercase tracking-widest text-bg transition-opacity hover:opacity-90"
            onClick={() => navigate('/signup')}
          >
            Create Your Legacy →
          </button>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-border py-12">
        <div className="mx-auto flex max-w-3xl justify-around px-8">
          {[
            { value: '<600ms', label: 'Response latency' },
            { value: '50+', label: 'Concurrent users' },
            { value: '2 min', label: 'Voice cloning' },
          ].map(({ value, label }) => (
            <div key={label} className="text-center">
              <p className="font-mono text-3xl font-bold text-green">{value}</p>
              <p className="mt-1 font-sans text-sm text-textdim">{label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section className="mx-auto max-w-4xl px-8 py-20">
        <h2 className="mb-12 text-center font-mono text-xs uppercase tracking-[0.3em] text-textdim">
          How It Works
        </h2>
        <div className="grid gap-8 md:grid-cols-3">
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
            <div key={step} className="rounded-lg border border-border bg-surface p-6">
              <p className="font-mono text-xs text-green">{step}</p>
              <h3 className="mt-2 font-mono text-base font-bold text-text">{title}</h3>
              <p className="mt-2 font-sans text-sm text-textdim">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border py-20 text-center">
        <h2 className="font-sans text-3xl font-bold text-text">
          Preserve someone's voice today.
        </h2>
        <button
          className="mt-8 rounded bg-green px-10 py-4 font-mono text-sm font-bold uppercase tracking-widest text-bg transition-opacity hover:opacity-90"
          onClick={() => navigate('/signup')}
        >
          Get Started Free →
        </button>
      </section>

      {/* Footer */}
      <footer className="border-t border-border px-8 py-6 text-center">
        <p className="font-mono text-xs text-muted">
          © 2026 EchoPersona. Built with care.
        </p>
      </footer>
    </div>
  )
}
