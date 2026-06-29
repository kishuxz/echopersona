import { DEFAULT_API_BASE } from '../constants'
import type {
  AdminStats,
  AdminPersonaRow,
  AdminPersonaDetail,
  AdminRelationship,
  AdminRelationshipCreate,
  ReEnrichResponse,
} from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE

function adminHeaders(): HeadersInit {
  const key = localStorage.getItem('adminKey') ?? ''
  return { 'Content-Type': 'application/json', 'X-Admin-Key': key }
}

async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...adminHeaders(), ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? `Admin API error ${res.status}`)
  }
  return res.json() as Promise<T>
}

export async function adminGetStats(): Promise<AdminStats> {
  return adminFetch<AdminStats>('/admin/stats')
}

export async function adminListPersonas(): Promise<AdminPersonaRow[]> {
  return adminFetch<AdminPersonaRow[]>('/admin/personas')
}

export async function adminGetPersona(personaId: string): Promise<AdminPersonaDetail> {
  return adminFetch<AdminPersonaDetail>(`/admin/personas/${personaId}`)
}

export async function adminReEnrich(personaId: string): Promise<ReEnrichResponse> {
  return adminFetch<ReEnrichResponse>(`/admin/personas/${personaId}/re-enrich`, {
    method: 'POST',
  })
}

export async function adminAddRelationship(
  personaId: string,
  body: AdminRelationshipCreate,
): Promise<AdminRelationship> {
  return adminFetch<AdminRelationship>(`/admin/personas/${personaId}/relationships`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function adminRemoveRelationship(
  personaId: string,
  listenerUserId: string,
): Promise<void> {
  await adminFetch<unknown>(`/admin/personas/${personaId}/relationships/${listenerUserId}`, {
    method: 'DELETE',
  })
}
