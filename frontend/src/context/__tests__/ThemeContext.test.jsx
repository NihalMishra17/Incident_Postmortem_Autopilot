import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider, useTheme } from '../ThemeContext'

function TestComponent() {
  const context = useTheme()
  if (!context) return <div>Context is null</div>
  return (
    <div>
      <div data-testid="theme">{context.theme}</div>
      <button onClick={context.toggle}>Toggle</button>
    </div>
  )
}

describe('ThemeContext', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('initializes theme from localStorage', () => {
    localStorage.setItem('pm-theme', 'dark')
    render(
      <ThemeProvider>
        <TestComponent />
      </ThemeProvider>
    )
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
  })

  it('falls back to prefers-color-scheme: dark when no stored value', () => {
    window.matchMedia = vi.fn().mockImplementation(query => ({
      matches: query === '(prefers-color-scheme: dark)',
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    render(
      <ThemeProvider>
        <TestComponent />
      </ThemeProvider>
    )
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
  })

  it('toggle() switches theme, updates localStorage, toggles dark class on documentElement', async () => {
    const user = userEvent.setup()

    render(
      <ThemeProvider>
        <TestComponent />
      </ThemeProvider>
    )

    // Get initial theme
    const initialTheme = screen.getByTestId('theme').textContent
    const initialIsDark = document.documentElement.classList.contains('dark')

    // Toggle
    await user.click(screen.getByRole('button', { name: /toggle/i }))
    const afterFirstToggle = screen.getByTestId('theme').textContent
    expect(afterFirstToggle).not.toBe(initialTheme)
    expect(localStorage.getItem('pm-theme')).toBe(afterFirstToggle)
    expect(document.documentElement.classList.contains('dark')).toBe(!initialIsDark)

    // Toggle back
    await user.click(screen.getByRole('button', { name: /toggle/i }))
    expect(screen.getByTestId('theme')).toHaveTextContent(initialTheme)
    expect(localStorage.getItem('pm-theme')).toBe(initialTheme)
    expect(document.documentElement.classList.contains('dark')).toBe(initialIsDark)
  })

  it('useTheme() outside provider returns null', () => {
    render(<TestComponent />)
    expect(screen.getByText('Context is null')).toBeInTheDocument()
  })
})
