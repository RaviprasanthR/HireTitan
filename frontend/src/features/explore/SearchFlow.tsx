import { Building2, CircleCheck, ListFilter, Search, Sparkles } from 'lucide-react'
import { Donut } from '@/components/Donut'
import { FlowChart } from '@/components/FlowChart'

/** Colours for the three outcomes: the reference palette's first three dark slots, validated
 * on the dark surface (lightness band, chroma, colour-blind and normal-vision separation, 3:1). */
const OUTCOME_COLOURS = {
  added: '#d95926',
  merged: '#3987e5',
  leftOut: '#199e70',
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

/** What happened to the jobs a search found: new, already known, left out. */
export function OutcomeDonut({
  added,
  merged,
  leftOut,
}: {
  added: number
  merged: number
  leftOut: number
}) {
  return (
    <Donut
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
