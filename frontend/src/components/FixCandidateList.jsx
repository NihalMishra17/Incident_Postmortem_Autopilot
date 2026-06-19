import { CheckCircle2 } from 'lucide-react'

export default function FixCandidateList({ fixes = [], selected, onSelect, customFix, onCustomFix }) {
  return (
    <div className="space-y-2">
      {fixes.map((f, i) => {
        const isSelected = selected === i
        const pct = Math.round((f.confidence || 0) * 100)
        return (
          <button
            key={i}
            type="button"
            onClick={() => onSelect(i)}
            className={[
              'w-full text-left rounded-card border p-3 transition-colors',
              isSelected
                ? 'border-pm-accent dark:border-pm-accent-dark bg-pm-accent/5'
                : 'border-pm-border dark:border-pm-border-dark bg-pm-surface dark:bg-pm-surface-dark hover:border-pm-accent/50',
            ].join(' ')}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-body text-pm-text dark:text-pm-text-dark leading-snug">{f.fix}</span>
              {isSelected && <CheckCircle2 size={14} className="text-pm-accent dark:text-pm-accent-dark shrink-0 mt-0.5" />}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <div className="flex-1 h-1 rounded-full bg-pm-border dark:bg-pm-border-dark overflow-hidden">
                <div
                  className="h-full rounded-full bg-pm-accent dark:bg-pm-accent-dark"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-meta text-pm-muted dark:text-pm-muted-dark shrink-0">{pct}%</span>
            </div>
            {f.reasoning && (
              <p className="mt-1.5 text-meta text-pm-muted dark:text-pm-muted-dark leading-snug">{f.reasoning}</p>
            )}
          </button>
        )
      })}

      <div
        className={[
          'rounded-card border transition-colors',
          selected === 'custom'
            ? 'border-pm-accent dark:border-pm-accent-dark'
            : 'border-pm-border dark:border-pm-border-dark',
        ].join(' ')}
      >
        <button
          type="button"
          onClick={() => onSelect('custom')}
          className="w-full text-left px-3 py-2 text-label text-pm-muted dark:text-pm-muted-dark font-medium"
        >
          Write your own fix
        </button>
        {selected === 'custom' && (
          <textarea
            rows={3}
            placeholder="Describe the fix applied…"
            value={customFix}
            onChange={e => onCustomFix(e.target.value)}
            className="w-full px-3 pb-3 text-body bg-transparent text-pm-text dark:text-pm-text-dark placeholder:text-pm-muted resize-none outline-none border-t border-pm-border dark:border-pm-border-dark"
          />
        )}
      </div>
    </div>
  )
}
