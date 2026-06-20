import '@testing-library/jest-dom'
import { vi, beforeEach } from 'vitest'

// Mock fetch globally
global.fetch = vi.fn()

// Mock window.matchMedia (not in happy-dom)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

beforeEach(() => {
  vi.mocked(global.fetch).mockReset()
  localStorage.clear()
})
