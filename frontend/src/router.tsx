import { createBrowserRouter, Navigate, useNavigate } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AuthPage } from './pages/AuthPage'
import { BillingPage } from './pages/BillingPage'
import { Dashboard } from './pages/Dashboard'
import { LandingPage } from './pages/LandingPage'
import { PersonaDetail } from './pages/PersonaDetail'
import { ConsentPage } from './pages/ConsentPage'
import { PersonaEdit } from './pages/PersonaEdit'

function StaticPage({ title, body }: { title: string; body: string }) {
  const navigate = useNavigate()
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-bg px-6 text-center">
      <span className="font-fraunces text-xl font-semibold text-text">{title}</span>
      <p className="max-w-sm font-sans text-sm text-textdim">{body}</p>
      <button
        className="font-sans text-sm text-accent underline-offset-2 hover:underline"
        onClick={() => navigate('/')}
      >
        ← Back to home
      </button>
    </div>
  )
}

function NotFoundPage() {
  const navigate = useNavigate()
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-bg px-6 text-center">
      <span className="font-mono text-5xl font-bold text-border">404</span>
      <span className="font-fraunces text-xl font-semibold text-text">Page not found</span>
      <p className="max-w-xs font-sans text-sm text-textdim">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <div className="flex gap-4">
        <button
          className="rounded-lg bg-accent px-5 py-2 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
          onClick={() => navigate('/')}
        >
          Go home
        </button>
        <button
          className="font-sans text-sm text-textdim transition-colors hover:text-text"
          onClick={() => navigate(-1)}
        >
          Go back
        </button>
      </div>
    </div>
  )
}

export const router = createBrowserRouter([
  { path: '/', element: <LandingPage /> },
  { path: '/login', element: <AuthPage mode="login" /> },
  { path: '/signup', element: <AuthPage mode="signup" /> },
  {
    path: '/dashboard',
    element: (
      <ProtectedRoute>
        <Dashboard />
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/persona/:personaId',
    element: (
      <ProtectedRoute>
        <PersonaDetail />
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/persona/:personaId/consent',
    element: (
      <ProtectedRoute>
        <ConsentPage />
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/persona/:personaId/edit',
    element: (
      <ProtectedRoute>
        <PersonaEdit />
      </ProtectedRoute>
    ),
  },
  {
    path: '/dashboard/billing',
    element: (
      <ProtectedRoute>
        <BillingPage />
      </ProtectedRoute>
    ),
  },
  { path: '/billing/success', element: <Navigate to="/dashboard/billing" replace /> },
  { path: '/billing/cancel', element: <Navigate to="/dashboard/billing" replace /> },
  {
    path: '/privacy',
    element: (
      <StaticPage
        title="Privacy Policy"
        body="We're finalizing our privacy policy. In the meantime, if you have questions about how we handle your data, reach out to us directly."
      />
    ),
  },
  {
    path: '/terms',
    element: (
      <StaticPage
        title="Terms of Service"
        body="We're finalizing our terms of service. By using EchoPersona during this early access period, you agree to use it responsibly."
      />
    ),
  },
  { path: '*', element: <NotFoundPage /> },
])
