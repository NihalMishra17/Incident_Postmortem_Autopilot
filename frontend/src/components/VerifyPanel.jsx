import { useState } from 'react'
import { CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import FixCandidateList from './FixCandidateList'

export default function VerifyPanel({ postmortem, onVerified }) {
  const [rootCause, setRootCause] = useState(postmortem.root_cause || '')
  const [selectedFix, setSelectedFix] = useState(null)
  const [customFix, setCustomFix] = useState('')
  const [verifiedBy, setVerifiedBy] = useState('')
  const [status, setStatus] = useState('idle')
  const [errorMsg, setErrorMsg] = useState('')

  const fixes = postmortem.suggested_fixes || []
  const alreadyVerified = postmortem.verified === true

  // Auto-select 'custom' when no ranked fixes exist; prevents null state in validation
  const effectiveSelectedFix = fixes.length === 0 ? 'custom' : selectedFix

  if (alreadyVerified) {
    return (
      <div className="rounded-card border border-pm-border dark:border-pm-border-dark bg-pm-surface dark:bg-pm-surface-dark p-4">
        <div className="flex items-center gap-2 text-pm-accent dark:text-pm-accent-dark">
          <CheckCircle2 size={14} />
          <span className="text-label font-medium">Verified</span>
        </div>
        <div className="mt-2 space-y-1.5">
          <p className="text-meta text-pm-muted dark:text-pm-muted-dark">
            by <span className="text-pm-text dark:text-pm-text-dark">{postmortem.verified_by}</span>
            {postmortem.verified_at && <> · {new Date(postmortem.verified_at).toLocaleString()}</>}
          </p>
          {postmortem.confirmed_root_cause && (
            <p className="text-meta text-pm-muted dark:text-pm-muted-dark">
              <span className="font-medium">Root cause: </span>{postmortem.confirmed_root_cause}
            </p>
          )}
          {postmortem.final_fix && (
            <p className="text-meta text-pm-muted dark:text-pm-muted-dark">
              <span className="font-medium">Fix: </span>{postmortem.final_fix}
              <span className="ml-1 text-pm-muted">({postmortem.final_fix_source})</span>
            </p>
          )}
        </div>
      </div>
    )
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!rootCause.trim()) { setErrorMsg('Root cause is required'); return }
    if (effectiveSelectedFix === null) { setErrorMsg('Select a fix or write your own'); return }
    if (effectiveSelectedFix === 'custom' && !customFix.trim()) { setErrorMsg('Write your custom fix'); return }
    if (!verifiedBy.trim()) { setErrorMsg('Verified by is required'); return }

    setStatus('loading')
    setErrorMsg('')

    const payload = {
      confirmed_root_cause: rootCause.trim(),
      verified_by: verifiedBy.trim(),
    }
    if (effectiveSelectedFix === 'custom') {
      payload.custom_fix = customFix.trim()
    } else {
      payload.selected_fix_index = effectiveSelectedFix
    }

    try {
      const res = await fetch(`/postmortems/${postmortem.id}/verify`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      setStatus('success')
      if (onVerified) onVerified()
    } catch (e) {
      setStatus('error')
      setErrorMsg(e.message)
    }
  }

  if (status === 'success') {
    return (
      <div className="rounded-card border border-pm-accent/30 dark:border-pm-accent-dark/30 bg-pm-accent/5 p-4 flex items-center gap-2 text-pm-accent dark:text-pm-accent-dark">
        <CheckCircle2 size={16} />
        <span className="text-label font-medium">Postmortem verified successfully</span>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <h3 className="text-label font-semibold text-pm-text dark:text-pm-text-dark uppercase tracking-wide">
        Verify Postmortem
      </h3>

      <div>
        <label className="block text-label text-pm-muted dark:text-pm-muted-dark mb-1">Confirmed root cause</label>
        <textarea
          rows={3}
          value={rootCause}
          onChange={e => setRootCause(e.target.value)}
          className="w-full rounded-card border border-pm-border dark:border-pm-border-dark bg-pm-surface dark:bg-pm-surface-dark px-3 py-2 text-body text-pm-text dark:text-pm-text-dark placeholder:text-pm-muted resize-none outline-none focus:border-pm-accent dark:focus:border-pm-accent-dark transition-colors"
          placeholder="Describe the root cause…"
        />
      </div>

      {fixes.length > 0 && (
        <div>
          <label className="block text-label text-pm-muted dark:text-pm-muted-dark mb-2">Select fix</label>
          <FixCandidateList
            fixes={fixes}
            selected={selectedFix}
            onSelect={setSelectedFix}
            customFix={customFix}
            onCustomFix={setCustomFix}
          />
        </div>
      )}

      {fixes.length === 0 && (
        <div>
          <label className="block text-label text-pm-muted dark:text-pm-muted-dark mb-1">Fix applied</label>
          <textarea
            rows={3}
            value={customFix}
            onChange={e => setCustomFix(e.target.value)}
            className="w-full rounded-card border border-pm-border dark:border-pm-border-dark bg-pm-surface dark:bg-pm-surface-dark px-3 py-2 text-body text-pm-text dark:text-pm-text-dark placeholder:text-pm-muted resize-none outline-none focus:border-pm-accent dark:focus:border-pm-accent-dark transition-colors"
            placeholder="Describe the fix applied…"
          />
        </div>
      )}

      <div>
        <label className="block text-label text-pm-muted dark:text-pm-muted-dark mb-1">Verified by</label>
        <input
          type="text"
          value={verifiedBy}
          onChange={e => setVerifiedBy(e.target.value)}
          placeholder="Your name or email"
          className="w-full rounded-card border border-pm-border dark:border-pm-border-dark bg-pm-surface dark:bg-pm-surface-dark px-3 py-2 text-body text-pm-text dark:text-pm-text-dark placeholder:text-pm-muted outline-none focus:border-pm-accent dark:focus:border-pm-accent-dark transition-colors"
        />
      </div>

      {errorMsg && (
        <div className="flex items-center gap-2 text-sev-critical">
          <AlertCircle size={13} />
          <span className="text-meta">{errorMsg}</span>
        </div>
      )}

      <button
        type="submit"
        disabled={status === 'loading'}
        className="flex items-center gap-2 rounded-card bg-pm-accent dark:bg-pm-accent-dark text-white px-4 py-2 text-label font-medium transition-opacity disabled:opacity-60 hover:opacity-90"
      >
        {status === 'loading' && <Loader2 size={13} className="animate-spin" />}
        Confirm & Verify
      </button>
    </form>
  )
}
