import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '../../context/ThemeContext'
import App from '../../App'
import * as usePostmortemsModule from '../../hooks/usePostmortems'
import * as usePostmortemModule from '../../hooks/usePostmortem'

vi.mock('../../hooks/usePostmortems')
vi.mock('../../hooks/usePostmortem')

function renderApp() {
  return render(
    <ThemeProvider>
      <App />
    </ThemeProvider>
  )
}

describe('App integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('App renders IncidentFeed and PostmortemDetail side by side', () => {
    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem: null,
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    renderApp()

    // IncidentFeed header - use getAllByText since "incidents" appears in multiple places
    expect(screen.getAllByText(/incidents/i)[0]).toBeInTheDocument()
    expect(screen.getByText(/select an incident/i)).toBeInTheDocument() // PostmortemDetail placeholder
  })

  it('clicking incident in feed -> PostmortemDetail shows that incident detail', async () => {
    const user = userEvent.setup()

    const postmortems = [
      { id: '1', service: 'auth-service', title: 'Auth failure', severity: 'HIGH', verified: false },
      { id: '2', service: 'payment-service', title: 'Payment timeout', severity: 'CRITICAL', verified: false },
    ]

    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems,
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    let selectedId = null
    const mockUsePostmortem = vi.spyOn(usePostmortemModule, 'usePostmortem')
    mockUsePostmortem.mockImplementation((id) => {
      selectedId = id
      if (!id) {
        return { postmortem: null, loading: false, error: null, refetch: vi.fn() }
      }
      const pm = postmortems.find(p => p.id === id)
      return {
        postmortem: pm ? { ...pm, root_cause: `Root cause for ${id}` } : null,
        loading: false,
        error: null,
        refetch: vi.fn(),
      }
    })

    renderApp()

    // Click first incident - get all "Auth failure" texts, first is in feed
    const authTexts = screen.getAllByText('Auth failure')
    const authButton = authTexts[0].closest('button')
    await user.click(authButton)

    // PostmortemDetail should show auth failure details - should have 2 instances now
    expect(screen.getAllByText('Auth failure')).toHaveLength(2)
    // Verify root cause is shown (appears in section and textarea)
    expect(screen.getAllByText('Root cause for 1')).toHaveLength(2)
  })

  it('theme toggle button -> switches dark/light class on html element', async () => {
    const user = userEvent.setup()

    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem: null,
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    renderApp()

    // Initially light (no dark class)
    expect(document.documentElement.classList.contains('dark')).toBe(false)

    // Click toggle button
    const toggleButton = screen.getByRole('button', { name: /toggle dark mode/i })
    await user.click(toggleButton)

    // Should now have dark class
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    // Click again
    await user.click(toggleButton)

    // Should remove dark class
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})
