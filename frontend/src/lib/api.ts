import { DEFAULT_API_BASE, DEFAULT_WS_BASE } from '../constants'
import { supabase } from './supabase'
import type { Persona, PersonaCreate, ConsentRecord, ConsentCreate, SuccessionRecord, SuccessionCreate, BillingStatus } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE

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

export async function updatePersona(personaId: string, updates: Partial<PersonaCreate>): Promise<Persona> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/persona/${personaId}`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error('Failed to update persona')
  return res.json()
}

export async function deletePersona(personaId: string): Promise<void> {
  const headers = await getAuthHeaders()
  await fetch(`${API_BASE}/persona/${personaId}`, {
    method: 'DELETE',
    headers,
  })
}

export async function getConsent(personaId: string): Promise<ConsentRecord | null> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/personas/${personaId}/consent`, { headers })
  if (res.status === 404) return null
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to fetch consent')
  }
  return res.json()
}

export async function saveConsent(personaId: string, data: ConsentCreate): Promise<ConsentRecord> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/personas/${personaId}/consent`, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to save consent')
  }
  return res.json()
}

export async function getSuccession(personaId: string): Promise<SuccessionRecord | null> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/personas/${personaId}/succession`, { headers })
  if (res.status === 404) return null
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to fetch succession')
  }
  return res.json()
}

export async function saveSuccession(personaId: string, data: SuccessionCreate): Promise<SuccessionRecord> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/personas/${personaId}/succession`, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to save succession')
  }
  return res.json()
}

export async function getBillingStatus(): Promise<BillingStatus> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/billing/status`, { headers })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function startCheckout(plan_tier: 'creator' | 'legacy'): Promise<void> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}/billing/checkout`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ plan_tier }),
  })
  if (!res.ok) throw new Error(await res.text())
  const { checkout_url } = await res.json()
  window.location.href = checkout_url
}

export async function buildWsUrl(
  sessionId: string,
  personaId: string,
): Promise<string> {
  const {
    data: { session },
  } = await supabase.auth.getSession()
  const token = session?.access_token ?? ''
  const base = import.meta.env.VITE_WS_BASE_URL ?? DEFAULT_WS_BASE
  return `${base}/ws/${sessionId}?persona_id=${personaId}&token=${encodeURIComponent(token)}`
}
