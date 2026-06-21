const THEME = {
  edge:       '#D6D1C2',
  hub:        '#8C8769',
  nodeStroke: '#D6D1C2',
  nodeFill:   '#F6F3E9',
  text:       '#8C8769',
  label:      '#2E2C22',
}

export default function BlastRadiusGraph({ affected_services = [] }) {
  const services = Array.isArray(affected_services)
    ? affected_services
    : typeof affected_services === 'string'
    ? affected_services.split(',').map(s => s.trim()).filter(Boolean)
    : []

  if (services.length === 0) return null

  const nodeW = 90
  const nodeH = 28
  const spacing = 16
  const totalW = services.length * nodeW + (services.length - 1) * spacing
  const svgW = Math.max(totalW, 160)
  const svgH = 100
  const centerX = svgW / 2
  const incidentY = 20
  const nodeY = 72

  return (
    <svg
      width={svgW}
      height={svgH}
      viewBox={`0 0 ${svgW} ${svgH}`}
      style={{ maxWidth: '100%', overflow: 'visible' }}
      aria-label="Blast radius graph"
    >
      {services.map((_, i) => {
        // Center nodes horizontally: (svgW - totalW) / 2 is left offset, then position i-th node
        const nx = (svgW - totalW) / 2 + i * (nodeW + spacing) + nodeW / 2
        return (
          <line
            key={i}
            x1={centerX} y1={incidentY + 8}
            x2={nx} y2={nodeY - nodeH / 2}
            stroke={THEME.edge}
            strokeWidth={1}
            strokeOpacity={0.8}
          />
        )
      })}
      <circle cx={centerX} cy={incidentY} r={8} fill={THEME.hub} fillOpacity={0.85} />
      <text x={centerX} y={incidentY - 12} textAnchor="middle" fontSize="10" fill={THEME.text} fontWeight="500">
        incident
      </text>
      {services.map((svc, i) => {
        const nx = (svgW - totalW) / 2 + i * (nodeW + spacing)
        return (
          <g key={i}>
            <rect
              x={nx} y={nodeY - nodeH / 2}
              width={nodeW} height={nodeH}
              rx={5} ry={5}
              fill={THEME.nodeFill}
              stroke={THEME.nodeStroke}
              strokeWidth={1}
            />
            <text
              x={nx + nodeW / 2} y={nodeY + 4}
              textAnchor="middle"
              fontSize="10"
              fill={THEME.label}
              fontFamily="Inter, system-ui, sans-serif"
            >
              {svc.length > 12 ? svc.slice(0, 11) + '…' : svc}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
