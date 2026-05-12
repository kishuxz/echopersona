import { useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const INTERVAL_MS = 10 * 60 * 1000  // 10 minutes

/**
 * Pings /health every 10 minutes to prevent Render free tier from sleeping.
 * No-op if the fetch fails (fire-and-forget).
 */
export function useKeepAlive() {
  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`${API_BASE}/health`).catch(() => {})
    }, INTERVAL_MS)
    return () => clearInterval(interval)
  }, [])
}
