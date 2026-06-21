import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
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
      { incident_id: '1', service: 'auth-service', title: 'Auth failure', severity: 'HIGH', verified: false },
      { incident_id: '2', service: 'payment-service', title: 'Payment timeout', severity: 'CRITICAL', verified: false },
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
      const pm = postmortems.find(p => p.incident_id === id)
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

describe('App mobile drawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('hamburger menu button renders in the document', () => {
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

    const hamburgerButton = screen.getByRole('button', { name: /open incident feed/i })
    expect(hamburgerButton).toBeInTheDocument()
  })

  it('clicking hamburger button opens drawer (drawerOpen becomes true)', async () => {
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

    const { container } = renderApp()

    // Initially drawer is closed (translate-x-full on mobile)
    const drawer = container.querySelector('aside')
    expect(drawer).toHaveClass('-translate-x-full')

    // Click hamburger button
    const hamburgerButton = screen.getByRole('button', { name: /open incident feed/i })
    await user.click(hamburgerButton)

    // Drawer should now be open (translate-x-0)
    expect(drawer).toHaveClass('translate-x-0')
    expect(drawer).not.toHaveClass('-translate-x-full')
  })

  it('clicking backdrop closes the drawer (drawerOpen becomes false)', async () => {
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

    const { container } = renderApp()

    // Open drawer first
    const hamburgerButton = screen.getByRole('button', { name: /open incident feed/i })
    await user.click(hamburgerButton)

    // Drawer is open
    const drawer = container.querySelector('aside')
    expect(drawer).toHaveClass('translate-x-0')

    // Click backdrop
    const backdrop = container.querySelector('.fixed.inset-0.bg-black\\/50')
    expect(backdrop).toBeInTheDocument()
    await user.click(backdrop)

    // Drawer should be closed
    expect(drawer).toHaveClass('-translate-x-full')
  })

  it('pressing Escape key closes the drawer when open', async () => {
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

    const { container } = renderApp()

    // Open drawer
    const hamburgerButton = screen.getByRole('button', { name: /open incident feed/i })
    await user.click(hamburgerButton)

    // Drawer is open
    const drawer = container.querySelector('aside')
    expect(drawer).toHaveClass('translate-x-0')

    // Press Escape
    fireEvent.keyDown(document, { key: 'Escape' })

    // Drawer should be closed
    expect(drawer).toHaveClass('-translate-x-full')
  })

  it('pressing Escape when drawer is closed does nothing / no errors', async () => {
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

    const { container } = renderApp()

    // Drawer is initially closed
    const drawer = container.querySelector('aside')
    expect(drawer).toHaveClass('-translate-x-full')

    // Press Escape - should not throw error
    expect(() => {
      fireEvent.keyDown(document, { key: 'Escape' })
    }).not.toThrow()

    // Drawer should still be closed
    expect(drawer).toHaveClass('-translate-x-full')
  })

  it('backdrop element has aria-hidden="true"', async () => {
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

    const { container } = renderApp()

    // Open drawer to show backdrop
    const hamburgerButton = screen.getByRole('button', { name: /open incident feed/i })
    await user.click(hamburgerButton)

    // Find backdrop and verify aria-hidden
    const backdrop = container.querySelector('.fixed.inset-0.bg-black\\/50')
    expect(backdrop).toHaveAttribute('aria-hidden', 'true')
  })

  it('selecting an incident in the feed closes the drawer', async () => {
    const user = userEvent.setup()

    const postmortems = [
      { incident_id: '1', service: 'auth-service', title: 'Auth failure', severity: 'HIGH', verified: false },
    ]

    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems,
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

    const { container } = renderApp()

    // Open drawer
    const hamburgerButton = screen.getByRole('button', { name: /open incident feed/i })
    await user.click(hamburgerButton)

    // Drawer is open
    const drawer = container.querySelector('aside')
    expect(drawer).toHaveClass('translate-x-0')

    // Click an incident
    const incidentButton = screen.getByText('Auth failure').closest('button')
    await user.click(incidentButton)

    // Drawer should be closed
    expect(drawer).toHaveClass('-translate-x-full')
  })

  it('sidebar has resizable drag handle and CSS variable for width', () => {
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

    const { container } = renderApp()

    // Find drag handle
    const dragHandle = container.querySelector('.cursor-col-resize')
    expect(dragHandle).toBeInTheDocument()
    expect(dragHandle).toHaveClass('hover:bg-pm-border')
    expect(dragHandle).toHaveClass('hidden')
    expect(dragHandle).toHaveClass('md:block')

    // Verify the aside has the CSS variable style attribute with initial width
    const aside = container.querySelector('aside')
    expect(aside).toHaveAttribute('style')
    expect(aside.getAttribute('style')).toContain('--sidebar-w')
    expect(aside.getAttribute('style')).toContain('240px') // default sidebarWidth
  })
})
