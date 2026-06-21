import { useState, useEffect } from 'react'
import { Moon, Sun, Menu } from 'lucide-react'
import { useTheme } from './context/ThemeContext'
import IncidentFeed from './components/IncidentFeed'
import PostmortemDetail from './components/PostmortemDetail'

/**
 * Main App component. Manages drawer state for mobile navigation and closes drawer on Escape key.
 */
export default function App() {
  const { theme, toggle } = useTheme()
  const [selectedId, setSelectedId] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    const handleKeyDown = (e) => { if (e.key === 'Escape' && drawerOpen) setDrawerOpen(false) }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [drawerOpen])

  return (
    <div className="h-full flex flex-col bg-pm-bg dark:bg-pm-bg-dark text-pm-text dark:text-pm-text-dark">
      <header className="h-10 shrink-0 flex items-center px-4 border-b border-pm-border dark:border-pm-border-dark bg-pm-surface dark:bg-pm-surface-dark">
        <button
          onClick={() => setDrawerOpen(true)}
          className="md:hidden p-1.5 rounded text-pm-muted dark:text-pm-muted-dark hover:text-pm-text dark:hover:text-pm-text-dark transition-colors mr-2"
          aria-label="Open incident feed"
        >
          <Menu size={14} />
        </button>
        <span className="text-label font-semibold text-pm-text dark:text-pm-text-dark tracking-tight">
          <span className="hidden md:inline">Incident Postmortem Autopilot</span>
          <span className="md:hidden">Incident PM</span>
        </span>
        <button
          onClick={toggle}
          className="ml-auto p-1.5 rounded text-pm-muted dark:text-pm-muted-dark hover:text-pm-text dark:hover:text-pm-text-dark transition-colors"
          aria-label="Toggle dark mode"
        >
          {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
        </button>
      </header>
      {drawerOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          aria-hidden="true"
          onClick={() => setDrawerOpen(false)}
        />
      )}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        <IncidentFeed selectedId={selectedId} onSelect={setSelectedId} drawerOpen={drawerOpen} setDrawerOpen={setDrawerOpen} />
        <PostmortemDetail incidentId={selectedId} />
      </div>
    </div>
  )
}
