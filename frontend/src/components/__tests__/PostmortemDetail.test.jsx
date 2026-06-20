import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '../../test/test-utils'
import PostmortemDetail from '../PostmortemDetail'
import * as usePostmortemModule from '../../hooks/usePostmortem'

vi.mock('../../hooks/usePostmortem')

describe('PostmortemDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('incidentId=null -> placeholder "Select an incident" text', () => {
    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem: null,
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<PostmortemDetail incidentId={null} />)

    expect(screen.getByText(/select an incident/i)).toBeInTheDocument()
  })

  it('loading=true -> spinner', () => {
    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    })

    render(<PostmortemDetail incidentId="1" />)

    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('error set -> error message', () => {
    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem: null,
      loading: false,
      error: 'Failed to load',
      refetch: vi.fn(),
    })

    render(<PostmortemDetail incidentId="1" />)

    expect(screen.getByText('Failed to load')).toBeInTheDocument()
  })

  it('full postmortem -> all sections (root_cause, timeline, remediation, prevention) rendered', () => {
    const postmortem = {
      id: '1',
      title: 'Database outage',
      service: 'auth-service',
      severity: 'CRITICAL',
      root_cause: 'Connection pool exhausted',
      timeline: '10:00 - Incident started\n10:15 - Team alerted',
      remediation: 'Increased connection pool size',
      prevention: 'Add monitoring',
      affected_services: ['auth-service', 'user-service'],
      verified: false,
    }

    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem,
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<PostmortemDetail incidentId="1" />)

    expect(screen.getByText('Database outage')).toBeInTheDocument()
    // Root cause appears both in section and in VerifyPanel's textarea, use getAllByText
    expect(screen.getAllByText(/connection pool exhausted/i)).toHaveLength(2)
    expect(screen.getByText(/10:00 - incident started/i)).toBeInTheDocument()
    expect(screen.getByText(/increased connection pool size/i)).toBeInTheDocument()
    expect(screen.getByText(/add monitoring/i)).toBeInTheDocument()
  })

  it('missing timeline + remediation fields -> those sections absent from DOM', () => {
    const postmortem = {
      id: '1',
      title: 'Database outage',
      service: 'auth-service',
      severity: 'CRITICAL',
      root_cause: 'Connection pool exhausted',
      prevention: 'Add monitoring',
      affected_services: [],
      verified: false,
    }

    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem,
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<PostmortemDetail incidentId="1" />)

    expect(screen.queryByText(/timeline/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/remediation/i)).not.toBeInTheDocument()
    expect(screen.getByText(/prevention/i)).toBeInTheDocument()
  })

  it('postmortem=null after loading -> renders null (no crash)', () => {
    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem: null,
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    const { container } = render(<PostmortemDetail incidentId="1" />)

    expect(container.firstChild).toBeNull()
  })

  it('severity badge shown', () => {
    const postmortem = {
      id: '1',
      title: 'Database outage',
      service: 'auth-service',
      severity: 'HIGH',
      root_cause: 'Connection pool exhausted',
      affected_services: [],
      verified: false,
    }

    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem,
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<PostmortemDetail incidentId="1" />)

    expect(screen.getByText('HIGH')).toBeInTheDocument()
  })

  it('BlastRadiusGraph rendered when affected_services present', () => {
    const postmortem = {
      id: '1',
      title: 'Database outage',
      service: 'auth-service',
      severity: 'CRITICAL',
      root_cause: 'Connection pool exhausted',
      affected_services: ['auth-service', 'user-service'],
      verified: false,
    }

    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem,
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    const { container } = render(<PostmortemDetail incidentId="1" />)

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('aria-label', 'Blast radius graph')
  })

  it('VerifyPanel rendered', () => {
    const postmortem = {
      id: '1',
      title: 'Database outage',
      service: 'auth-service',
      severity: 'CRITICAL',
      root_cause: 'Connection pool exhausted',
      affected_services: [],
      verified: false,
    }

    vi.spyOn(usePostmortemModule, 'usePostmortem').mockReturnValue({
      postmortem,
      loading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<PostmortemDetail incidentId="1" />)

    expect(screen.getByText(/verify postmortem/i)).toBeInTheDocument()
  })
})
