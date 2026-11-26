import { Building2, CircleCheck, ListFilter, Mail, Search, Sparkles } from 'lucide-react'
import { Donut } from '@/components/Donut'
import { FlowChart } from '@/components/FlowChart'

/** Colours for the three outcomes: new jobs carry the accent, the rest are neutral steps. They are
 * not pipeline stages, so no stage colour is used here (FR-004). */
const OUTCOME_COLOURS = {
  added: 'var(--ht-accent)',
  merged: 'var(--ht-text-secondary)',
  leftOut: 'var(--ht-text-muted)',
} as const

export type FlowCounts = {
  companiesRead: number
  companiesTotal: number
  toCheck: number
  jobsFound: number
  byRules: number
  judgedByAi: number
  byAi: number
  added: number
  merged: number
}

/** A search as a flow chart: companies read, jobs found, the rules, the AI check, new jobs. */
export function SearchFlow({ counts: c }: { counts: FlowCounts }) {
  return (
    <FlowChart
      label="How the search went"
      steps={[
        {
          key: 'companies',
          icon: Building2,
          title: 'Companies read',
          value: `${c.companiesRead} of ${c.companiesTotal}`,
          note: c.toCheck > 0 ? `${c.toCheck} to check by hand` : undefined,
        },
        { key: 'found', icon: Search, title: 'Jobs found', value: String(c.jobsFound) },
        { key: 'rules', icon: ListFilter, title: 'Your rules', value: `${c.byRules} left out` },
        {
          key: 'ai',
          icon: Sparkles,
          title: 'AI check',
          value: `${c.judgedByAi} checked`,
          note: `${c.byAi} left out`,
        },
        {
          key: 'new',
          icon: CircleCheck,
          title: 'New jobs',
          value: String(c.added),
          note: `${c.merged} already known`,
        },
      ]}
    />
  )
}

export type MailFlowCounts = {
  emailsRead: number
  emailsNew: number // the emails this check had not read before
  unreadable: number
  alreadyRead: number
  jobsFound: number
  byRules: number
  added: number
  merged: number
}

/** A mail check as a flow chart: emails read, jobs found, the rules, new jobs. */
export function MailFlow({ counts: c }: { counts: MailFlowCounts }) {
  return (
    <FlowChart
      label="How the mail check went"
      steps={[
        {
          key: 'emails',
          icon: Mail,
          title: 'Emails read',
          value: `${c.emailsRead} of ${c.emailsNew}`,
          note:
            c.unreadable > 0
              ? `${c.unreadable} could not be read`
              : c.alreadyRead > 0
                ? `${c.alreadyRead} read before`
                : undefined,
        },
        { key: 'found', icon: Search, title: 'Jobs found', value: String(c.jobsFound) },
        { key: 'rules', icon: ListFilter, title: 'Your rules', value: `${c.byRules} left out` },
        {
          key: 'new',
          icon: CircleCheck,
          title: 'New jobs',
          value: String(c.added),
          note: `${c.merged} already known`,
        },
      ]}
    />
  )
}

/** What happened to the jobs a search found: new, already known, left out. */
export function OutcomeDonut({
  added,
  merged,
  leftOut,
  compact = false,
}: {
  added: number
  merged: number
  leftOut: number
  compact?: boolean
}) {
  return (
    <Donut
      compact={compact}
      caption="What happened to the jobs found"
      totalLabel="jobs found"
      ariaLabel={`${added} new, ${merged} already known, ${leftOut} left out`}
      parts={[
        { key: 'added', label: 'New jobs', value: added, colour: OUTCOME_COLOURS.added },
        { key: 'merged', label: 'Already known', value: merged, colour: OUTCOME_COLOURS.merged },
        { key: 'leftOut', label: 'Left out', value: leftOut, colour: OUTCOME_COLOURS.leftOut },
      ]}
    />
  )
}
