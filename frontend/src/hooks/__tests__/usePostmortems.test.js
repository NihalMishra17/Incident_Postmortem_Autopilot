import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { usePostmortems } from '../usePostmortems'

describe('usePostmortems', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('initial state: loading=true, postmortems=[]', () => {
    global.fetch = vi.fn(() => new Promise(() => {})) // Never resolves
    const { result } = renderHook(() => usePostmortems())
    expect(result.current.loading).toBe(true)
    expect(result.current.postmortems).toEqual([])
    expect(result.current.error).toBe(null)
  })

  it('successful fetch populates postmortems, sets loading=false', async () => {
    const mockData = [
      { id: '1', title: 'Incident 1', verified: false, generated_at: '2026-06-20T10:00:00Z' },
      { id: '2', title: 'Incident 2', verified: false, generated_at: '2026-06-20T11:00:00Z' },
    ]
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    })

    const { result } = renderHook(() => usePostmortems())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.postmortems).toHaveLength(2)
    expect(result.current.error).toBe(null)
  })

  it('sorts unverified first', async () => {
    const mockData = [
      { id: '1', title: 'Verified', verified: true, generated_at: '2026-06-20T12:00:00Z' },
      { id: '2', title: 'Unverified new', verified: false, generated_at: '2026-06-20T11:00:00Z' },
      { id: '3', title: 'Unverified old', verified: false, generated_at: '2026-06-20T10:00:00Z' },
    ]
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    })

    const { result } = renderHook(() => usePostmortems())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.postmortems[0].id).toBe('2') // Unverified newest
    expect(result.current.postmortems[1].id).toBe('3') // Unverified older
    expect(result.current.postmortems[2].id).toBe('1') // Verified
  })

  it('fetch error sets error, loading=false', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    })

    const { result } = renderHook(() => usePostmortems())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('HTTP 500')
    expect(result.current.postmortems).toEqual([])
  })

  it('polling: triggers refetch every 10 seconds', async () => {
    vi.useFakeTimers()
    const mockData = [{ id: '1', title: 'Incident 1', verified: false }]
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    })

    const { unmount } = renderHook(() => usePostmortems())

    // Flush initial async fetch (timers + microtasks)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(global.fetch).toHaveBeenCalledTimes(1)

    // Trigger the 10-second interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000)
    })
    expect(global.fetch).toHaveBeenCalledTimes(2)

    unmount()
  })

  it('empty array response: postmortems=[], loading=false, error=null', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
    })

    const { result } = renderHook(() => usePostmortems())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.postmortems).toEqual([])
    expect(result.current.error).toBe(null)
  })
})
