import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { usePostmortem } from '../usePostmortem'

describe('usePostmortem', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches by ID on mount', async () => {
    const mockData = { id: '1', title: 'Test Incident', root_cause: 'Test cause' }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    })

    const { result } = renderHook(() => usePostmortem('1'))

    expect(result.current.loading).toBe(true)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.postmortem).toEqual(mockData)
    expect(result.current.error).toBe(null)
    expect(global.fetch).toHaveBeenCalledWith('/postmortems/1')
  })

  it('null ID -> no fetch called', () => {
    global.fetch = vi.fn()

    const { result } = renderHook(() => usePostmortem(null))

    expect(result.current.loading).toBe(false)
    expect(result.current.postmortem).toBe(null)
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('undefined ID -> no fetch called', () => {
    global.fetch = vi.fn()

    const { result } = renderHook(() => usePostmortem(undefined))

    expect(result.current.loading).toBe(false)
    expect(result.current.postmortem).toBe(null)
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('refetch() re-fetches', async () => {
    const mockData = { id: '1', title: 'Test Incident' }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    })

    const { result } = renderHook(() => usePostmortem('1'))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(global.fetch).toHaveBeenCalledTimes(1)

    // Call refetch
    result.current.refetch()

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(2)
    })
  })
})
