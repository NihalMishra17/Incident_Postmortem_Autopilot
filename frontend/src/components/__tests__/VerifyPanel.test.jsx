import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '../../test/test-utils'
import userEvent from '@testing-library/user-event'
import VerifyPanel from '../VerifyPanel'

describe('VerifyPanel', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('renders form with root_cause textarea and verified_by input', () => {
    const postmortem = {
      incident_id: '1',
      root_cause: 'Initial cause',
      verified: false,
    }

    render(<VerifyPanel postmortem={postmortem} onVerified={vi.fn()} />)

    expect(screen.getByPlaceholderText(/describe the root cause/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/your name or email/i)).toBeInTheDocument()
  })

  it('with suggested_fixes -> FixCandidateList shown', () => {
    const postmortem = {
      incident_id: '1',
      root_cause: 'Initial cause',
      verified: false,
      suggested_fixes: [
        { fix: 'Restart service', confidence: 0.85 },
      ],
    }

    render(<VerifyPanel postmortem={postmortem} onVerified={vi.fn()} />)

    expect(screen.getByText('Select fix')).toBeInTheDocument()
    expect(screen.getByText('Restart service')).toBeInTheDocument()
  })

  it('without suggested_fixes (empty/undefined) -> standalone custom textarea, no FixCandidateList', () => {
    const postmortem = {
      incident_id: '1',
      root_cause: 'Initial cause',
      verified: false,
    }

    render(<VerifyPanel postmortem={postmortem} onVerified={vi.fn()} />)

    expect(screen.queryByText('Select fix')).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText(/describe the fix applied/i)).toBeInTheDocument()
  })

  it('already verified (postmortem.verified=true) -> form hidden, verified info shown', () => {
    const postmortem = {
      incident_id: '1',
      verified: true,
      verified_by: 'alice@example.com',
      confirmed_root_cause: 'Database overload',
      final_fix: 'Added index',
      final_fix_source: 'custom',
    }

    render(<VerifyPanel postmortem={postmortem} onVerified={vi.fn()} />)

    expect(screen.getByText(/verified/i)).toBeInTheDocument()
    expect(screen.getByText('alice@example.com')).toBeInTheDocument()
    expect(screen.getByText(/database overload/i)).toBeInTheDocument()
    expect(screen.getByText(/added index/i)).toBeInTheDocument()

    // Form should not be present
    expect(screen.queryByPlaceholderText(/describe the root cause/i)).not.toBeInTheDocument()
  })

  it('submit with selected fix -> PATCH called with { selected_fix_index, verified_by, root_cause }', async () => {
    const user = userEvent.setup()
    const onVerified = vi.fn()
    const postmortem = {
      incident_id: '1',
      root_cause: 'Initial cause',
      verified: false,
      suggested_fixes: [
        { fix: 'Restart service', confidence: 0.85 },
        { fix: 'Increase memory', confidence: 0.65 },
      ],
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    })

    render(<VerifyPanel postmortem={postmortem} onVerified={onVerified} />)

    // Select second fix
    await user.click(screen.getByRole('button', { name: /increase memory/i }))

    // Fill form
    await user.clear(screen.getByPlaceholderText(/describe the root cause/i))
    await user.type(screen.getByPlaceholderText(/describe the root cause/i), 'Confirmed cause')
    await user.type(screen.getByPlaceholderText(/your name or email/i), 'bob@example.com')

    // Submit
    await user.click(screen.getByRole('button', { name: /confirm & verify/i }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/postmortems/1/verify',
        expect.objectContaining({
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            confirmed_root_cause: 'Confirmed cause',
            verified_by: 'bob@example.com',
            selected_fix_index: 1,
          }),
        })
      )
    })

    await waitFor(() => {
      expect(onVerified).toHaveBeenCalled()
    })
  })

  it('submit with custom fix -> PATCH called with { custom_fix, verified_by, root_cause }', async () => {
    const user = userEvent.setup()
    const onVerified = vi.fn()
    const postmortem = {
      incident_id: '1',
      root_cause: 'Initial cause',
      verified: false,
      suggested_fixes: [
        { fix: 'Restart service', confidence: 0.85 },
      ],
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    })

    render(<VerifyPanel postmortem={postmortem} onVerified={onVerified} />)

    // Select custom fix
    await user.click(screen.getByRole('button', { name: /write your own fix/i }))
    await user.type(screen.getByPlaceholderText(/describe the fix applied/i), 'Custom solution')

    // Fill form
    await user.clear(screen.getByPlaceholderText(/describe the root cause/i))
    await user.type(screen.getByPlaceholderText(/describe the root cause/i), 'Confirmed cause')
    await user.type(screen.getByPlaceholderText(/your name or email/i), 'charlie@example.com')

    // Submit
    await user.click(screen.getByRole('button', { name: /confirm & verify/i }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/postmortems/1/verify',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({
            confirmed_root_cause: 'Confirmed cause',
            verified_by: 'charlie@example.com',
            custom_fix: 'Custom solution',
          }),
        })
      )
    })

    await waitFor(() => {
      expect(onVerified).toHaveBeenCalled()
    })
  })

  it('validation: missing required field -> error message shown, no PATCH called', async () => {
    const user = userEvent.setup()
    const postmortem = {
      incident_id: '1',
      root_cause: '',
      verified: false,
    }

    render(<VerifyPanel postmortem={postmortem} onVerified={vi.fn()} />)

    // Submit without filling fields
    await user.click(screen.getByRole('button', { name: /confirm & verify/i }))

    await waitFor(() => {
      expect(screen.getByText(/root cause is required/i)).toBeInTheDocument()
    })

    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('API error -> error message shown', async () => {
    const user = userEvent.setup()
    const postmortem = {
      incident_id: '1',
      root_cause: 'Initial cause',
      verified: false,
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Validation error' }),
    })

    render(<VerifyPanel postmortem={postmortem} onVerified={vi.fn()} />)

    await user.type(screen.getByPlaceholderText(/describe the root cause/i), 'Confirmed')
    await user.type(screen.getByPlaceholderText(/describe the fix applied/i), 'Fix')
    await user.type(screen.getByPlaceholderText(/your name or email/i), 'dave@example.com')

    await user.click(screen.getByRole('button', { name: /confirm & verify/i }))

    await waitFor(() => {
      expect(screen.getByText(/validation error/i)).toBeInTheDocument()
    })
  })

  it('success -> onVerified callback called', async () => {
    const user = userEvent.setup()
    const onVerified = vi.fn()
    const postmortem = {
      incident_id: '1',
      root_cause: 'Initial cause',
      verified: false,
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    })

    render(<VerifyPanel postmortem={postmortem} onVerified={onVerified} />)

    await user.type(screen.getByPlaceholderText(/describe the root cause/i), 'Confirmed')
    await user.type(screen.getByPlaceholderText(/describe the fix applied/i), 'Fix')
    await user.type(screen.getByPlaceholderText(/your name or email/i), 'eve@example.com')

    await user.click(screen.getByRole('button', { name: /confirm & verify/i }))

    await waitFor(() => {
      expect(onVerified).toHaveBeenCalled()
    })
  })

  it('loading state -> button disabled during fetch', async () => {
    const user = userEvent.setup()
    const postmortem = {
      incident_id: '1',
      root_cause: 'Initial cause',
      verified: false,
    }

    // Make fetch hang
    global.fetch = vi.fn(() => new Promise(() => {}))

    render(<VerifyPanel postmortem={postmortem} onVerified={vi.fn()} />)

    await user.type(screen.getByPlaceholderText(/describe the root cause/i), 'Confirmed')
    await user.type(screen.getByPlaceholderText(/describe the fix applied/i), 'Fix')
    await user.type(screen.getByPlaceholderText(/your name or email/i), 'frank@example.com')

    const submitButton = screen.getByRole('button', { name: /confirm & verify/i })
    await user.click(submitButton)

    // Button should be disabled
    await waitFor(() => {
      expect(submitButton).toBeDisabled()
    })
  })
})
