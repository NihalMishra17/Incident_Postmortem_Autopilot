import { formatDistanceToNow } from 'date-fns'
import { usePostmortems } from '../hooks/usePostmortems'
import { RefreshCw } from 'lucide-react'

const SEV_DOT = {
  CRITICAL: 'bg-sev-critical',
  HIGH: 'bg-sev-high',
  MEDIUM: 'bg-pm-muted',
  LOW: 'bg-pm-muted',
}

function relativeTime(str) {
  if (!str) return ''
  try {
    return formatDistanceToNow(new Date(str), { addSuffix: true })
  } catch {
    return ''
  }
}

export default function IncidentFeed({ selectedId, onSelect }) {
  const { postmortems, loading, error } = usePostmortems()

  return (
    <aside className="w-[220px] shrink-0 h-full flex flex-col border-r border-pm-border dark:border-pm-border-dark bg-pm-bg dark:bg-pm-bg-dark">
      <div className="px-3 py-3 border-b border-pm-border dark:border-pm-border-dark flex items-center justify-between">
        <span className="text-label font-semibold text-pm-text dark:text-pm-text-dark uppercase tracking-wide">
          Incidents
        </span>
        {loading && <RefreshCw size={11} className="text-pm-muted animate-spin" />}
      </div>
      <div className="flex-1 overflow-y-auto">
        {error && <p className="px-3 py-4 text-meta text-sev-critical">{error}</p>}
        {!error && postmortems.length === 0 && !loading && (
          <p className="px-3 py-4 text-meta text-pm-muted dark:text-pm-muted-dark">No incidents yet.</p>
        )}
        {postmortems.map(pm => {
          const isSelected = pm.id === selectedId
          const dotClass = SEV_DOT[pm.severity] || 'bg-pm-muted'
          const ts = relativeTime(pm.generated_at || pm.verified_at)
          return (
            <button
              key={pm.id}
              onClick={() => onSelect(pm.id)}
              className={[
                'w-full text-left px-3 py-2.5 border-b border-pm-border/50 dark:border-pm-border-dark/50',
                'hover:bg-pm-surface dark:hover:bg-pm-surface-dark transition-colors',
                isSelected ? 'bg-pm-surface dark:bg-pm-surface-dark' : '',
              ].join(' ')}
            >
              <div className="flex items-center gap-2 mb-0.5">
                <span className={`w-[5px] h-[5px] rounded-full shrink-0 ${dotClass}`} />
                <span className="text-meta text-pm-muted dark:text-pm-muted-dark truncate">{pm.service}</span>
                {pm.verified && (
                  <span className="ml-auto text-[10px] text-pm-accent dark:text-pm-accent-dark font-medium shrink-0">✓</span>
                )}
              </div>
              <p className="text-body text-pm-text dark:text-pm-text-dark truncate leading-snug pl-[13px]">
                {pm.title || pm.id}
              </p>
              {ts && (
                <p className="text-meta text-pm-muted dark:text-pm-muted-dark pl-[13px] mt-0.5">{ts}</p>
              )}
            </button>
          )
        })}
      </div>
    </aside>
  )
}
