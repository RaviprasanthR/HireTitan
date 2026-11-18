import { BadgeCheck, CalendarClock, Layers, MessageCircleQuestion, Send } from 'lucide-react'
import { Donut } from '@/components/Donut'
import { ChartRow, FlowChart } from '@/components/FlowChart'
import { usePipelineSummary } from './api'

/** One colour per status, in pipeline order: blue, aqua, yellow, violet, red from the dataviz
 * reference palette (dark steps), validated on the dark surface, including the ring's wrap-around
 * pair (failed next to inquired). The hues follow the Status pills where the check allows. */
const STATUS_COLOURS = {
  inquired: '#3987e5',
  applied: '#199e70',
  scheduled: '#c98500',
  cleared: '#9085e9',
  failed: '#e66767',
} as const

/** The pipeline at a glance: a flow from inquired to a cleared round, and a donut of every job by
 * its status. Shown above the In pipeline list once something is in it. */
export function PipelineChart() {
  const summary = usePipelineSummary()
  const s = summary.data
  if (!s || s.total === 0) return null
  return (
    <ChartRow>
      <FlowChart
        label="Your pipeline"
        steps={[
          { key: 'total', icon: Layers, title: 'In pipeline', value: String(s.total) },
          {
            key: 'inquired',
            icon: MessageCircleQuestion,
            title: 'Inquired',
            value: String(s.inquired),
          },
          { key: 'applied', icon: Send, title: 'Applied', value: String(s.applied) },
          {
            key: 'scheduled',
            icon: CalendarClock,
            title: 'Interview scheduled',
            value: String(s.scheduled),
          },
          {
            key: 'cleared',
            icon: BadgeCheck,
            title: 'Round cleared',
            value: String(s.cleared),
            note: s.failed > 0 ? `${s.failed} failed` : undefined,
          },
        ]}
      />
      <Donut
        caption="Your jobs by status"
        totalLabel="jobs in pipeline"
        ariaLabel={`${s.inquired} inquired, ${s.applied} applied, ${s.scheduled} interview scheduled, ${s.cleared} round cleared, ${s.failed} failed`}
        parts={[
          {
            key: 'inquired',
            label: 'Inquired',
            value: s.inquired,
            colour: STATUS_COLOURS.inquired,
          },
          { key: 'applied', label: 'Applied', value: s.applied, colour: STATUS_COLOURS.applied },
          {
            key: 'scheduled',
            label: 'Interview scheduled',
            value: s.scheduled,
            colour: STATUS_COLOURS.scheduled,
          },
          {
            key: 'cleared',
            label: 'Round cleared',
            value: s.cleared,
            colour: STATUS_COLOURS.cleared,
          },
          { key: 'failed', label: 'Failed', value: s.failed, colour: STATUS_COLOURS.failed },
        ]}
      />
    </ChartRow>
  )
}
