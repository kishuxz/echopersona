import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export function LandingPage() {
  const navigate = useNavigate()
  const { user, loading } = useAuth()
  const isLoggedIn = !loading && !!user

  return (
    <div className="min-h-screen bg-bg text-text">
      {/* Nav */}
      <nav className="flex items-center justify-between border-b border-border bg-surface/95 backdrop-blur-sm px-8 py-4 shadow-card sticky top-0 z-40">
        <span className="font-fraunces text-xl font-semibold text-text">
          EchoPersona
        </span>
        <div className="flex items-center gap-4">
          {isLoggedIn ? (
            <button
              className="rounded-lg bg-accent px-4 py-2 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
              onClick={() => navigate('/dashboard')}
            >
              Go to Dashboard →
            </button>
          ) : (
            <>
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
            </>
          )}
        </div>
      </nav>

      {/* Hero — full viewport */}
      <section className="hero-gradient relative min-h-[calc(100vh-61px)] flex items-center overflow-hidden">
        <div className="mx-auto max-w-6xl w-full px-8 py-16 flex flex-col lg:flex-row items-center lg:items-start gap-12 lg:gap-8">

          {/* Left — headline */}
          <div className="flex-1 text-center lg:text-left">
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-1.5 shadow-card">
              <span className="h-1.5 w-1.5 rounded-full bg-green" />
              <span className="font-sans text-[11px] text-textdim">
                ~1.5s response — feels like a real conversation
              </span>
            </div>
            <h1 className="mt-2 font-fraunces text-5xl font-semibold leading-[1.1] tracking-tight text-text lg:text-6xl">
              Talk to the people<br />you love.{' '}
              <span className="text-green">Forever.</span>
            </h1>
            <p className="mx-auto mt-6 max-w-lg font-sans text-lg text-textdim lg:mx-0">
              Real-time AI personas built from memories, stories, and voice.
              Sub-second latency that makes every conversation feel present.
            </p>
            <div className="mt-10 flex items-center justify-center gap-4 lg:justify-start">
              <button
                className="rounded-lg bg-accent px-8 py-3.5 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
                onClick={() => navigate(isLoggedIn ? '/dashboard' : '/signup')}
              >
                {isLoggedIn ? 'Go to Dashboard →' : 'Create Your Legacy →'}
              </button>
            </div>
          </div>

          {/* Right — phone/card mockup */}
          <div className="flex-shrink-0 hidden sm:block w-[320px] select-none">
            <div className="rounded-2xl bg-white p-4 shadow-lg">

              {/* Card header: avatar + name + live */}
              <div className="mb-4 flex items-center gap-3 border-b border-gray-100 pb-3">
                <img
                  src="https://api.dicebear.com/7.x/adventurer/svg?seed=GrandpaJoe&backgroundColor=ffdfbf"
                  className="w-10 h-10 rounded-full"
                  alt="Grandpa Joe"
                />
                <div>
                  <p className="font-sans text-sm font-semibold text-text">Grandpa Joe</p>
                  <div className="flex items-center gap-1">
                    <span
                      className="inline-block h-1.5 w-1.5 rounded-full bg-green"
                      style={{ animation: 'blink 1s step-end infinite' }}
                    />
                    <span className="font-sans text-xs text-green">Live</span>
                  </div>
                </div>
              </div>

              {/* Chat bubbles */}
              <div className="flex flex-col gap-3">
                {/* User bubble */}
                <div className="float-a self-end max-w-[85%]">
                  <div className="rounded-2xl rounded-br-sm bg-accent px-4 py-3 shadow-card-hover">
                    <p className="font-sans text-sm text-white leading-relaxed">
                      Tell me about your first job
                    </p>
                  </div>
                  <p className="mt-1 text-right font-mono text-[10px] text-muted">You</p>
                </div>

                {/* Persona bubble */}
                <div className="float-b self-start max-w-[90%]">
                  <div className="mb-1 flex items-center gap-1.5">
                    <img
                      src="https://api.dicebear.com/7.x/adventurer/svg?seed=GrandpaJoe&backgroundColor=ffdfbf"
                      className="w-7 h-7 rounded-full"
                      alt="GJ"
                    />
                    <span className="font-mono text-[10px] text-muted">Grandpa Joe</span>
                  </div>
                  <div className="rounded-2xl rounded-bl-sm border border-border bg-surface px-4 py-3 shadow-card-hover">
                    <p className="font-sans text-sm text-text leading-relaxed">
                      I remember it like yesterday — 1987, downtown Chicago. Started at the warehouse at 6am…
                    </p>
                  </div>
                </div>

                {/* Second user bubble */}
                <div className="float-a self-end max-w-[80%]" style={{ animationDelay: '1.5s' }}>
                  <div className="rounded-2xl rounded-br-sm bg-accent px-4 py-3 shadow-card-hover">
                    <p className="font-sans text-sm text-white leading-relaxed">
                      What did you love most about it?
                    </p>
                  </div>
                  <p className="mt-1 text-right font-mono text-[10px] text-muted">You</p>
                </div>
              </div>

            </div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-border bg-surface py-12 shadow-card">
        <div className="mx-auto max-w-4xl px-8">
          <div className="grid grid-cols-2 gap-8 md:grid-cols-4">
            {[
              { value: '~1.5s',          label: 'Response latency' },
              { value: '50+',            label: 'Concurrent users' },
              { value: '2 min',          label: 'Voice cloning' },
              { value: 'RAG-powered',    label: 'Memory retrieval' },
            ].map(({ value, label }, i) => (
              <div key={label} className={`text-center ${i < 3 ? 'md:border-r md:border-border' : ''}`}>
                <p className="font-mono text-3xl font-bold text-text">{value}</p>
                <p className="mt-1.5 font-sans text-sm text-textdim">{label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="mx-auto max-w-4xl px-8 py-20">
        <h2 className="mb-12 text-center font-fraunces text-2xl font-semibold text-text">
          How It Works
        </h2>
        <div className="relative grid gap-6 md:grid-cols-3">
          {/* Connecting line — desktop only */}
          <div className="absolute top-8 left-[16.67%] right-[16.67%] hidden h-px bg-border md:block" />

          {[
            {
              step: '01',
              title: 'Upload Stories',
              desc: 'Share memories, personality traits, and speaking style to define the persona.',
              icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                  <line x1="8" y1="7" x2="16" y2="7" />
                  <line x1="8" y1="11" x2="16" y2="11" />
                  <line x1="8" y1="15" x2="12" y2="15" />
                </svg>
              ),
            },
            {
              step: '02',
              title: 'Clone Voice',
              desc: '30 seconds of audio is all it takes to recreate a unique voice.',
              icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                  <rect x="9" y="2" width="6" height="12" rx="3" />
                  <path d="M5 10a7 7 0 0 0 14 0" />
                  <line x1="12" y1="19" x2="12" y2="23" />
                  <line x1="8" y1="23" x2="16" y2="23" />
                </svg>
              ),
            },
            {
              step: '03',
              title: 'Start Talking',
              desc: 'Real-time voice conversation with ~1.5s latency, in their voice.',
              icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              ),
            },
          ].map(({ step, title, desc, icon }) => (
            <div key={step} className="how-card relative rounded-xl border border-border bg-surface p-6 shadow-card">
              <div className="relative z-10 mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-elevated text-textdim">
                {icon}
              </div>
              <p className="font-mono text-xs text-muted">{step}</p>
              <h3 className="mt-2 font-fraunces text-lg font-semibold text-text">{title}</h3>
              <p className="mt-2 font-sans text-sm leading-relaxed text-textdim">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Built for Speed — dark section */}
      <section className="bg-ink py-20">
        <div className="mx-auto max-w-4xl px-8">
          <h2 className="mb-3 text-center font-fraunces text-2xl font-semibold text-white">
            Real-time. Every time.
          </h2>
          <p className="mb-12 text-center font-sans text-sm text-white/50">
            Built on Groq, ElevenLabs, and RAG — the fastest stack available
          </p>

          <div className="flex flex-col items-center gap-4 md:flex-row md:items-stretch md:justify-center">
            {[
              { label: 'Hear you',  time: '~240ms', sub: 'Speech recognition' },
              { label: 'Thinks',   time: '~340ms', sub: 'LLM + memory recall' },
              { label: 'Responds', time: '~1s',    sub: 'Voice synthesis' },
            ].map(({ label, time, sub }, i) => (
              <div key={label} className="flex flex-col items-center gap-2 flex-1">
                {i > 0 && (
                  <div className="hidden md:flex absolute items-center">
                    <span className="text-white/20 text-xl">→</span>
                  </div>
                )}
                <div className="w-full max-w-[180px] rounded-xl border border-white/10 bg-white/5 p-5 text-center">
                  <p className="font-sans text-xs uppercase tracking-widest text-white/40 mb-1">{sub}</p>
                  <p className="font-fraunces text-xl font-semibold text-white">{label}</p>
                  <p className="mt-2 font-mono text-lg text-green">{time}</p>
                </div>
                {i < 2 && (
                  <div className="hidden md:block text-white/20 text-2xl absolute" style={{ transform: 'translateX(196px)' }}>→</div>
                )}
              </div>
            ))}
          </div>

          {/* Arrow connectors */}
          <div className="mt-6 hidden md:flex items-center justify-center gap-4">
            <div className="flex items-center gap-2 text-white/20 font-mono text-xs">
              <span>240ms</span>
              <span>→</span>
              <span>+340ms</span>
              <span>→</span>
              <span>+1s total</span>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border bg-elevated py-20 text-center">
        <h2 className="font-fraunces text-3xl font-semibold text-text">
          Preserve someone's voice today.
        </h2>
        <p className="mx-auto mt-3 max-w-md font-sans text-sm text-textdim">
          Upload their stories, clone their voice, and keep the conversation going.
        </p>
        <button
          className="mt-8 rounded-lg bg-accent px-10 py-4 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
          onClick={() => navigate(isLoggedIn ? '/dashboard' : '/signup')}
        >
          {isLoggedIn ? 'Go to Dashboard →' : 'Get Started Free →'}
        </button>
      </section>

      {/* Footer */}
      <footer className="border-t border-border bg-surface px-8 py-8">
        <div className="mx-auto flex max-w-4xl flex-col items-center gap-4 md:flex-row md:justify-between">
          <span className="font-fraunces text-base font-semibold text-text">EchoPersona</span>
          <nav className="flex items-center gap-6">
            <button
              className="font-sans text-sm text-textdim transition-colors hover:text-text"
              onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
            >
              Home
            </button>
            <button
              className="font-sans text-sm text-textdim transition-colors hover:text-text"
              onClick={() => navigate('/dashboard')}
            >
              Dashboard
            </button>
            <a
              href="https://github.com/kishuxz/echopersona"
              target="_blank"
              rel="noopener noreferrer"
              className="font-sans text-sm text-textdim transition-colors hover:text-text"
            >
              GitHub
            </a>
          </nav>
          <p className="font-sans text-xs text-muted">© 2026 EchoPersona. Built with care.</p>
        </div>
      </footer>
    </div>
  )
}
