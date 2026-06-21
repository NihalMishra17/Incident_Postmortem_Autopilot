import { useState, useEffect, useCallback } from 'react'

export function usePostmortems() {
  const [postmortems, setPostmortems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchAll = useCallback(async () => {
    try {
      const res = await fetch('/postmortems')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      // Sort: unverified incidents first, then by recency (newest first)
      const sorted = [...data].sort((a, b) => {
        if (a.verified !== b.verified) return a.verified ? 1 : -1
        const ta = a.generated_at || a.incident_id || ''
        const tb = b.generated_at || b.incident_id || ''
        return tb.localeCompare(ta)
      })
      setPostmortems(sorted)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 10000)
    return () => clearInterval(interval)
  }, [fetchAll])

  return { postmortems, loading, error, refetch: fetchAll }
}
