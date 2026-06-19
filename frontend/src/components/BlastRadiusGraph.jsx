const SEV_COLORS = {
  CRITICAL: '#B5482F',
  HIGH: '#A8782C',
  MEDIUM: '#8C8769',
  LOW: '#8C8769',
}

export default function BlastRadiusGraph({ affected_services = [], severity = 'MEDIUM' }) {
  const services = Array.isArray(affected_services)
    ? affected_services
    : typeof affected_services === 'string'
    ? affected_services.split(',').map(s => s.trim()).filter(Boolean)
    : []

  if (services.length === 0) return null

  const edgeColor = SEV_COLORS[severity] || SEV_COLORS.MEDIUM
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
            stroke={edgeColor}
            strokeWidth={1}
            strokeOpacity={0.6}
          />
        )
      })}
      <circle cx={centerX} cy={incidentY} r={8} fill={edgeColor} fillOpacity={0.9} />
      <text x={centerX} y={incidentY - 12} textAnchor="middle" fontSize="10" fill={edgeColor} fontWeight="500">
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
              fill="none"
              stroke={edgeColor}
              strokeWidth={1}
              strokeOpacity={0.5}
            />
            <text
              x={nx + nodeW / 2} y={nodeY + 4}
              textAnchor="middle"
              fontSize="10"
              fill={edgeColor}
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
