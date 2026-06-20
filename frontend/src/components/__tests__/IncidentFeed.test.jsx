import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '../../test/test-utils'
import userEvent from '@testing-library/user-event'
import IncidentFeed from '../IncidentFeed'
import * as usePostmortemsModule from '../../hooks/usePostmortems'

vi.mock('../../hooks/usePostmortems')

describe('IncidentFeed', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loading state -> spinner shown', () => {
    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    })

    render(<IncidentFeed selectedId={null} onSelect={vi.fn()} />)

    // RefreshCw spinner
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('error state -> error message', () => {
    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems: [],
      loading: false,
      error: 'Network error',
      refetch: vi.fn(),
    })

    render(<IncidentFeed selectedId={null} onSelect={vi.fn()} />)

    expect(screen.getByText('Network error')).toBeInTheDocument()
  })

  it('empty + not loading -> "No incidents yet"', () => {
    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<IncidentFeed selectedId={null} onSelect={vi.fn()} />)

    expect(screen.getByText(/no incidents yet/i)).toBeInTheDocument()
  })

  it('renders incident list with service name and title', () => {
    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems: [
        { id: '1', service: 'auth-service', title: 'Auth failure', severity: 'HIGH', verified: false },
        { id: '2', service: 'payment-service', title: 'Payment timeout', severity: 'CRITICAL', verified: false },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<IncidentFeed selectedId={null} onSelect={vi.fn()} />)

    expect(screen.getByText('auth-service')).toBeInTheDocument()
    expect(screen.getByText('Auth failure')).toBeInTheDocument()
    expect(screen.getByText('payment-service')).toBeInTheDocument()
    expect(screen.getByText('Payment timeout')).toBeInTheDocument()
  })

  it('severity dot present', () => {
    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems: [
        { id: '1', service: 'auth-service', title: 'Auth failure', severity: 'CRITICAL', verified: false },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    const { container } = render(<IncidentFeed selectedId={null} onSelect={vi.fn()} />)

    const dot = container.querySelector('.bg-sev-critical')
    expect(dot).toBeInTheDocument()
  })

  it('verified checkmark for verified incidents', () => {
    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems: [
        { id: '1', service: 'auth-service', title: 'Auth failure', severity: 'HIGH', verified: true },
        { id: '2', service: 'payment-service', title: 'Payment timeout', severity: 'CRITICAL', verified: false },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<IncidentFeed selectedId={null} onSelect={vi.fn()} />)

    // Checkmark should appear for verified incident
    const buttons = screen.getAllByRole('button')
    const verifiedButton = buttons.find(b => b.textContent.includes('✓'))
    expect(verifiedButton).toBeInTheDocument()
  })

  it('calls onSelect when incident clicked', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()

    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems: [
        { id: '1', service: 'auth-service', title: 'Auth failure', severity: 'HIGH', verified: false },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<IncidentFeed selectedId={null} onSelect={onSelect} />)

    const button = screen.getByText('Auth failure').closest('button')
    await user.click(button)

    expect(onSelect).toHaveBeenCalledWith('1')
  })

  it('relative timestamp renders deterministically', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-20T00:00:00Z'))

    // Now is 2026-06-20T00:00:00Z
    // Incident 5 min ago
    const fiveMinAgo = new Date('2026-06-19T23:55:00Z').toISOString()

    vi.spyOn(usePostmortemsModule, 'usePostmortems').mockReturnValue({
      postmortems: [
        { id: '1', service: 'auth-service', title: 'Auth failure', severity: 'HIGH', verified: false, generated_at: fiveMinAgo },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<IncidentFeed selectedId={null} onSelect={vi.fn()} />)

    expect(screen.getByText(/5 minutes ago/i)).toBeInTheDocument()

    vi.useRealTimers()
  })
})
