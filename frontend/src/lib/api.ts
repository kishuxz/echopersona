import { supabase } from './supabase'
import type { Persona, PersonaCreate } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function getAuthHeaders(): Promise<HeadersInit> {
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${session.access_token}`,
  }
}

async function getAuthHeadersNoContentType(): Promise<HeadersInit> {
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')
  return { Authorization: `Bearer ${session.access_token}` }
}

export async function createPersona(data: PersonaCreate): Promise<Persona> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/persona/create`, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to create persona')
  }
  return res.json()
}

export async function listPersonas(): Promise<Persona[]> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/persona/`, { headers })
  if (!res.ok) throw new Error('Failed to fetch personas')
  return res.json()
}

export async function getPersona(personaId: string): Promise<Persona> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/persona/${personaId}`, { headers })
  if (!res.ok) throw new Error('Persona not found')
  return res.json()
}

export async function uploadVoice(personaId: string, files: File[] | FileList): Promise<Persona> {
  const authHeader = await getAuthHeadersNoContentType()
  const formData = new FormData()
  Array.from(files).forEach((f) => formData.append('files', f))
  const res = await fetch(`${API_BASE}/persona/${personaId}/upload-voice`, {
    method: 'POST',
    headers: authHeader,
    body: formData,
  })
  if (!res.ok) throw new Error('Failed to upload voice')
  return res.json()
}

export async function uploadAvatar(personaId: string, file: File): Promise<Persona> {
  const authHeader = await getAuthHeadersNoContentType()
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${API_BASE}/persona/${personaId}/upload-avatar`, {
    method: 'POST',
    headers: authHeader,
    body: formData,
  })
  if (!res.ok) throw new Error('Failed to upload avatar')
  return res.json()
}

export async function saveSimliFaceId(personaId: string, faceId: string): Promise<Persona> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/persona/${personaId}/simli-face`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ face_id: faceId }),
  })
  if (!res.ok) throw new Error('Failed to save Simli face ID')
  return res.json()
}

export async function deletePersona(personaId: string): Promise<void> {
  const headers = await getAuthHeaders()
  await fetch(`${API_BASE}/persona/${personaId}`, {
    method: 'DELETE',
    headers,
  })
}

export async function buildWsUrl(
  sessionId: string,
  personaId: string,
): Promise<string> {
  const {
    data: { session },
  } = await supabase.auth.getSession()
  const token = session?.access_token ?? ''
  const base = import.meta.env.VITE_WS_BASE_URL ?? 'ws://localhost:8000'
  return `${base}/ws/${sessionId}?persona_id=${personaId}&token=${encodeURIComponent(token)}`
}
