import { useEffect, useRef } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { usePostmortems } from '../hooks/usePostmortems'
import { RefreshCw } from 'lucide-react'

const SEV_DOT = {
  CRITICAL: 'bg-sev-critical',
  HIGH: 'bg-sev-high',
  MEDIUM: 'bg-sev-medium',
  LOW: 'bg-sev-low',
}

function relativeTime(str) {
  if (!str) return ''
  try {
    return formatDistanceToNow(new Date(str), { addSuffix: true })
  } catch {
    return ''
  }
}

/**
 * IncidentFeed displays a list of postmortems with drag-to-resize on desktop via right-edge drag handle. On mobile, renders as a fixed-position drawer with slide-in animation; on desktop (md+), renders as a sidebar. Closes drawer on incident selection.
 * @param {string} selectedId - Currently selected incident ID
 * @param {function} onSelect - Callback to update selected incident
 * @param {boolean} drawerOpen - Whether drawer is open (mobile only)
 * @param {function} setDrawerOpen - Callback to toggle drawer state
 * @param {number} sidebarWidth - Current sidebar width in pixels (desktop only)
 * @param {function} setSidebarWidth - Callback to update sidebar width
 */
export default function IncidentFeed({ selectedId, onSelect, drawerOpen, setDrawerOpen, sidebarWidth, setSidebarWidth }) {
  const { postmortems, loading, error } = usePostmortems()
  const handlersRef = useRef({})

  const handleMouseDown = (e) => {
    e.preventDefault()
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    let latestWidth = sidebarWidth
    const handleMouseMove = (e) => {
      latestWidth = Math.min(400, Math.max(180, e.clientX))
      setSidebarWidth(latestWidth)
    }
    const handleMouseUp = () => {
      localStorage.setItem('sidebarWidth', String(latestWidth))
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', handlersRef.current.move)
      document.removeEventListener('mouseup', handlersRef.current.up)
    }
    handlersRef.current = { move: handleMouseMove, up: handleMouseUp }
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }

  useEffect(() => {
    return () => {
      if (handlersRef.current.move) {
        document.removeEventListener('mousemove', handlersRef.current.move)
        document.removeEventListener('mouseup', handlersRef.current.up)
      }
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [])

  return (
    <aside style={{ '--sidebar-w': sidebarWidth + 'px' }} className={`fixed inset-y-0 left-0 z-50 w-80 transition-transform duration-200 md:relative md:inset-y-auto md:left-auto md:z-auto md:w-[var(--sidebar-w)] md:translate-x-0 ${drawerOpen ? 'translate-x-0' : '-translate-x-full'} overscroll-contain shrink-0 flex flex-col border-r border-pm-border dark:border-pm-border-dark bg-pm-bg dark:bg-pm-bg-dark`}>
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
          const isSelected = pm.incident_id === selectedId
          const dotClass = SEV_DOT[pm.severity?.toUpperCase()] || 'bg-pm-muted'
          const ts = relativeTime(pm.generated_at || pm.verified_at)
          return (
            <button
              key={pm.incident_id}
              onClick={() => {
                onSelect(pm.incident_id)
                setDrawerOpen(false)
              }}
              className={[
                'w-full text-left px-3 py-2.5 border-b border-pm-border/50 dark:border-pm-border-dark/50',
                'hover:bg-pm-surface dark:hover:bg-pm-surface-dark transition-colors',
                isSelected ? 'bg-pm-surface dark:bg-pm-surface-dark' : '',
              ].join(' ')}
            >
              <div className="flex items-center gap-2 mb-0.5">
                <span className={`w-2 h-2 rounded-full shrink-0 ${dotClass}`} />
                <span className="text-meta text-pm-muted dark:text-pm-muted-dark truncate">{pm.service}</span>
                {pm.verified && (
                  <span className="ml-auto text-[10px] text-pm-accent dark:text-pm-accent-dark font-medium shrink-0">✓</span>
                )}
              </div>
              <p className="text-body text-pm-text dark:text-pm-text-dark truncate leading-snug pl-[13px]">
                {pm.title || pm.incident_id}
              </p>
              {ts && (
                <p className="text-meta text-pm-muted dark:text-pm-muted-dark pl-[13px] mt-0.5">{ts}</p>
              )}
            </button>
          )
        })}
      </div>
      <div
        className="absolute top-0 right-0 h-full w-1 cursor-col-resize bg-transparent hover:bg-pm-border hidden md:block"
        onMouseDown={handleMouseDown}
      />
    </aside>
  )
}
