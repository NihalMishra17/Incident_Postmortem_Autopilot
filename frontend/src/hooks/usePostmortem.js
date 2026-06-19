import { useState, useEffect, useCallback } from 'react'

export function usePostmortem(id) {
  const [postmortem, setPostmortem] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchOne = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const res = await fetch(`/postmortems/${id}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setPostmortem(data)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    fetchOne()
  }, [fetchOne])

  return { postmortem, loading, error, refetch: fetchOne }
}
