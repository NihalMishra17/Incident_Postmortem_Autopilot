import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '../../test/test-utils'
import userEvent from '@testing-library/user-event'
import FixCandidateList from '../FixCandidateList'

describe('FixCandidateList', () => {
  const fixes = [
    { fix: 'Restart the service', confidence: 0.85, reasoning: 'Most common fix' },
    { fix: 'Increase memory', confidence: 0.65 },
    { fix: 'Update config', confidence: 0.45 },
  ]

  it('renders all fix candidates', () => {
    render(
      <FixCandidateList
        fixes={fixes}
        selected={null}
        onSelect={vi.fn()}
        customFix=""
        onCustomFix={vi.fn()}
      />
    )

    expect(screen.getByText('Restart the service')).toBeInTheDocument()
    expect(screen.getByText('Increase memory')).toBeInTheDocument()
    expect(screen.getByText('Update config')).toBeInTheDocument()
  })

  it('confidence percentage shown (e.g. 0.85 -> "85%")', () => {
    render(
      <FixCandidateList
        fixes={fixes}
        selected={null}
        onSelect={vi.fn()}
        customFix=""
        onCustomFix={vi.fn()}
      />
    )

    expect(screen.getByText('85%')).toBeInTheDocument()
    expect(screen.getByText('65%')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('clicking candidate calls onSelect with correct index', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()

    render(
      <FixCandidateList
        fixes={fixes}
        selected={null}
        onSelect={onSelect}
        customFix=""
        onCustomFix={vi.fn()}
      />
    )

    const button = screen.getByRole('button', { name: /increase memory/i })
    await user.click(button)

    expect(onSelect).toHaveBeenCalledWith(1)
  })

  it('selected candidate shows checkmark/selected state', () => {
    render(
      <FixCandidateList
        fixes={fixes}
        selected={0}
        onSelect={vi.fn()}
        customFix=""
        onCustomFix={vi.fn()}
      />
    )

    // CheckCircle2 icon appears inside the selected button only
    const selectedButton = screen.getByRole('button', { name: /restart the service/i })
    const unselectedButton = screen.getByRole('button', { name: /increase memory/i })
    expect(selectedButton.querySelector('svg')).toBeInTheDocument()
    expect(unselectedButton.querySelector('svg')).not.toBeInTheDocument()
  })

  it('custom fix option: renders textarea, onCustomFix called on type', async () => {
    const user = userEvent.setup()
    const onCustomFix = vi.fn()

    render(
      <FixCandidateList
        fixes={fixes}
        selected="custom"
        onSelect={vi.fn()}
        customFix=""
        onCustomFix={onCustomFix}
      />
    )

    const textarea = screen.getByPlaceholderText(/describe the fix/i)
    expect(textarea).toBeInTheDocument()

    await user.type(textarea, 'My custom fix')

    expect(onCustomFix).toHaveBeenCalled()
  })
})
