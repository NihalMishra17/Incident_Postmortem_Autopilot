import { describe, it, expect } from 'vitest'
import { render } from '../../test/test-utils'
import BlastRadiusGraph from '../BlastRadiusGraph'

describe('BlastRadiusGraph', () => {
  it('empty affected_services -> renders nothing', () => {
    const { container } = render(<BlastRadiusGraph affected_services={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('array of 3 services -> SVG with 3 nodes', () => {
    const { container } = render(
      <BlastRadiusGraph affected_services={['service-a', 'service-b', 'service-c']} />
    )
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()

    // Should have 3 service rects
    const rects = container.querySelectorAll('rect')
    expect(rects).toHaveLength(3)

    // Should have 3 service text labels
    const texts = container.querySelectorAll('text')
    expect(texts.length).toBeGreaterThanOrEqual(3) // Incident label + 3 service labels
  })

  it('comma-separated string -> parses into array correctly', () => {
    const { container } = render(
      <BlastRadiusGraph affected_services="auth-service, payment-service, user-service" />
    )

    const rects = container.querySelectorAll('rect')
    expect(rects).toHaveLength(3)
  })

  it('long name truncated to 12 chars + ellipsis', () => {
    const { container } = render(
      <BlastRadiusGraph affected_services={['very-long-service-name-that-should-be-truncated']} />
    )

    // Service name is truncated to 11 chars + ellipsis (total 12 visible chars including ellipsis)
    const texts = Array.from(container.querySelectorAll('text'))
    const truncatedText = texts.find(t => t.textContent && t.textContent.endsWith('…'))

    expect(truncatedText).toBeDefined()
    expect(truncatedText.textContent).toBe('very-long-s…')
  })

  it('hub circle uses neutral theme color #8C8769', () => {
    const { container } = render(
      <BlastRadiusGraph affected_services={['service-a']} />
    )

    const svg = container.querySelector('svg')
    const serialized = svg.outerHTML
    expect(serialized).toContain('#8C8769')
  })
})
