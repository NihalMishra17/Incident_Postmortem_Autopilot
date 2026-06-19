import { usePostmortem } from '../hooks/usePostmortem'
import BlastRadiusGraph from './BlastRadiusGraph'
import VerifyPanel from './VerifyPanel'
import { Loader2 } from 'lucide-react'

const SEV_DOT = {
  CRITICAL: 'bg-sev-critical',
  HIGH: 'bg-sev-high',
  MEDIUM: 'bg-pm-muted',
  LOW: 'bg-pm-muted',
}

const SEV_LABEL = {
  CRITICAL: 'text-sev-critical',
  HIGH: 'text-sev-high',
  MEDIUM: 'text-pm-muted',
  LOW: 'text-pm-muted',
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-label font-semibold text-pm-muted dark:text-pm-muted-dark uppercase tracking-wide mb-1.5">
        {title}
      </h3>
      {children}
    </div>
  )
}

export default function PostmortemDetail({ incidentId }) {
  const { postmortem, loading, error, refetch } = usePostmortem(incidentId)

  if (!incidentId) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-meta text-pm-muted dark:text-pm-muted-dark">Select an incident</p>
      </div>
    )
  }
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={18} className="text-pm-muted animate-spin" />
      </div>
    )
  }
  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-meta text-sev-critical">{error}</p>
      </div>
    )
  }
  if (!postmortem) return null

  const dotClass = SEV_DOT[postmortem.severity] || 'bg-pm-muted'
  const labelClass = SEV_LABEL[postmortem.severity] || 'text-pm-muted'
  const affectedServices = Array.isArray(postmortem.affected_services)
    ? postmortem.affected_services
    : postmortem.affected_services
    ? [postmortem.affected_services]
    : []

  return (
    <main className="flex-1 overflow-y-auto bg-pm-bg dark:bg-pm-bg-dark">
      <div className="max-w-2xl mx-auto px-6 py-6 space-y-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className={`w-[5px] h-[5px] rounded-full shrink-0 ${dotClass}`} />
            <span className={`text-label font-medium ${labelClass}`}>{postmortem.severity}</span>
            <span className="text-meta text-pm-muted dark:text-pm-muted-dark">· {postmortem.service}</span>
          </div>
          <h1 className="text-[17px] font-semibold text-pm-text dark:text-pm-text-dark leading-snug">
            {postmortem.title}
          </h1>
        </div>

        <div className="h-px bg-pm-border dark:bg-pm-border-dark" />

        {postmortem.root_cause && (
          <Section title="Root cause">
            <p className="text-body text-pm-text dark:text-pm-text-dark whitespace-pre-wrap">{postmortem.root_cause}</p>
          </Section>
        )}

        {postmortem.timeline && (
          <Section title="Timeline">
            <p className="text-body text-pm-text dark:text-pm-text-dark whitespace-pre-wrap">{postmortem.timeline}</p>
          </Section>
        )}

        {affectedServices.length > 0 && (
          <Section title="Blast radius">
            <div className="rounded-card border border-pm-border dark:border-pm-border-dark bg-pm-surface dark:bg-pm-surface-dark p-4 overflow-x-auto">
              <BlastRadiusGraph affected_services={affectedServices} severity={postmortem.severity} />
            </div>
          </Section>
        )}

        {postmortem.remediation && (
          <Section title="Remediation">
            <p className="text-body text-pm-text dark:text-pm-text-dark whitespace-pre-wrap">{postmortem.remediation}</p>
          </Section>
        )}

        {postmortem.prevention && (
          <Section title="Prevention">
            <p className="text-body text-pm-text dark:text-pm-text-dark whitespace-pre-wrap">{postmortem.prevention}</p>
          </Section>
        )}

        <div className="h-px bg-pm-border dark:bg-pm-border-dark" />

        <VerifyPanel postmortem={postmortem} onVerified={refetch} />
      </div>
    </main>
  )
}
