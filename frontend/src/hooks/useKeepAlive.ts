import { useEffect } from 'react'
import { DEFAULT_API_BASE, KEEP_ALIVE_INTERVAL_MS } from '../constants'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE

/**
 * Pings /health every 10 minutes to prevent Render free tier from sleeping.
 * No-op if the fetch fails (fire-and-forget).
 */
export function useKeepAlive() {
  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`${API_BASE}/health`).catch(() => {})
    }, KEEP_ALIVE_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [])
}
