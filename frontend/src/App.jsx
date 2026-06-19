import { useState } from 'react'
import { Moon, Sun } from 'lucide-react'
import { useTheme } from './context/ThemeContext'
import IncidentFeed from './components/IncidentFeed'
import PostmortemDetail from './components/PostmortemDetail'

export default function App() {
  const { theme, toggle } = useTheme()
  const [selectedId, setSelectedId] = useState(null)

  return (
    <div className="h-full flex flex-col bg-pm-bg dark:bg-pm-bg-dark text-pm-text dark:text-pm-text-dark">
      <header className="h-10 shrink-0 flex items-center px-4 border-b border-pm-border dark:border-pm-border-dark bg-pm-surface dark:bg-pm-surface-dark">
        <span className="text-label font-semibold text-pm-text dark:text-pm-text-dark tracking-tight">
          Incident Postmortem Autopilot
        </span>
        <button
          onClick={toggle}
          className="ml-auto p-1.5 rounded text-pm-muted dark:text-pm-muted-dark hover:text-pm-text dark:hover:text-pm-text-dark transition-colors"
          aria-label="Toggle dark mode"
        >
          {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
        </button>
      </header>
      <div className="flex-1 flex overflow-hidden">
        <IncidentFeed selectedId={selectedId} onSelect={setSelectedId} />
        <PostmortemDetail incidentId={selectedId} />
      </div>
    </div>
  )
}
