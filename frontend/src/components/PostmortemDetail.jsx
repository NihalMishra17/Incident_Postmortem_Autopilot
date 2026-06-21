import { useState, useEffect } from 'react'
import { usePostmortem } from '../hooks/usePostmortem'
import BlastRadiusGraph from './BlastRadiusGraph'
import VerifyPanel from './VerifyPanel'
import { Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

const SEV_DOT = {
  CRITICAL: 'bg-sev-critical',
  HIGH: 'bg-sev-high',
  MEDIUM: 'bg-sev-medium',
  LOW: 'bg-sev-low',
}

const SEV_LABEL = {
  CRITICAL: 'text-sev-critical',
  HIGH: 'text-sev-high',
  MEDIUM: 'text-sev-medium',
  LOW: 'text-sev-low',
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
  const [graphModalOpen, setGraphModalOpen] = useState(false)

  useEffect(() => {
    if (!graphModalOpen) return
    const handler = (e) => { if (e.key === 'Escape') setGraphModalOpen(false) }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [graphModalOpen])

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

  const dotClass = SEV_DOT[postmortem.severity?.toUpperCase()] || 'bg-pm-muted'
  const labelClass = SEV_LABEL[postmortem.severity?.toUpperCase()] || 'text-pm-muted'
  const affectedServices = Array.isArray(postmortem.affected_services)
    ? postmortem.affected_services
    : postmortem.affected_services
    ? [postmortem.affected_services]
    : []

  return (
    <main className="flex-1 overflow-y-auto bg-pm-bg dark:bg-pm-bg-dark">
      <div className="max-w-2xl mx-auto px-4 md:px-6 py-4 md:py-6 space-y-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className={`w-2 h-2 rounded-full shrink-0 ${dotClass}`} />
            <span className={`text-label font-medium ${labelClass}`}>{postmortem.severity}</span>
            <span className="text-meta text-pm-muted dark:text-pm-muted-dark">· {postmortem.service}</span>
          </div>
          <h1 className="text-[17px] md:text-[19px] font-semibold text-pm-text dark:text-pm-text-dark leading-snug">
            {postmortem.title}
          </h1>
        </div>

        <div className="h-px bg-pm-border dark:bg-pm-border-dark" />

        {postmortem.root_cause && (
          <Section title="Root cause">
            <div className="prose prose-sm max-w-none text-pm-text dark:text-pm-text-dark [&_*]:text-inherit">
              <ReactMarkdown>{postmortem.root_cause}</ReactMarkdown>
            </div>
          </Section>
        )}

        {postmortem.timeline && (
          <Section title="Timeline">
            <div className="prose prose-sm max-w-none text-pm-text dark:text-pm-text-dark [&_*]:text-inherit">
              <ReactMarkdown>{postmortem.timeline}</ReactMarkdown>
            </div>
          </Section>
        )}

        {affectedServices.length > 0 && (
          <Section title="Blast radius">
            <div
              onClick={() => setGraphModalOpen(true)}
              className="rounded-card border border-pm-border dark:border-pm-border-dark bg-pm-surface dark:bg-pm-surface-dark p-4 overflow-x-auto cursor-pointer hover:bg-pm-border/10 dark:hover:bg-pm-border-dark/10 transition-colors"
            >
              <BlastRadiusGraph affected_services={affectedServices} />
            </div>
          </Section>
        )}

        {graphModalOpen && (
          <>
            <div
              className="fixed inset-0 z-50 bg-black/40"
              onClick={() => setGraphModalOpen(false)}
            />
            <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none">
              <div
                className="pointer-events-auto bg-pm-surface dark:bg-pm-surface-dark border border-pm-border dark:border-pm-border-dark rounded-card shadow-2xl p-8 w-[90vw] max-w-3xl"
                onClick={(e) => e.stopPropagation()}
              >
                <BlastRadiusGraph affected_services={affectedServices} width={620} height={360} />
              </div>
            </div>
          </>
        )}

        {postmortem.remediation && (
          <Section title="Remediation">
            <div className="prose prose-sm max-w-none text-pm-text dark:text-pm-text-dark [&_*]:text-inherit">
              <ReactMarkdown>{postmortem.remediation}</ReactMarkdown>
            </div>
          </Section>
        )}

        {postmortem.prevention && (
          <Section title="Prevention">
            <div className="prose prose-sm max-w-none text-pm-text dark:text-pm-text-dark [&_*]:text-inherit">
              <ReactMarkdown>{postmortem.prevention}</ReactMarkdown>
            </div>
          </Section>
        )}

        <div className="h-px bg-pm-border dark:bg-pm-border-dark" />

        <VerifyPanel postmortem={postmortem} onVerified={refetch} />
      </div>
    </main>
  )
}
