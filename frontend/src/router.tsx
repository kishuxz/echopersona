import { createBrowserRouter, Navigate } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AuthPage } from './pages/AuthPage'
import { Dashboard } from './pages/Dashboard'
import { LandingPage } from './pages/LandingPage'
import { PersonaDetail } from './pages/PersonaDetail'
import { ConsentPage } from './pages/ConsentPage'
import { PersonaEdit } from './pages/PersonaEdit'

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
  { path: '*', element: <Navigate to="/" replace /> },
])
