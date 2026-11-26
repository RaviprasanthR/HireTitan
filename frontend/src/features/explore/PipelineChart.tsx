import { BadgeCheck, CalendarClock, Layers, MessageCircleQuestion, Send } from 'lucide-react'
import { Donut } from '@/components/Donut'
import { ChartRow, FlowChart } from '@/components/FlowChart'
import { STAGES, type StageKey } from '@/theme/stages'
import { usePipelineSummary } from './api'

/** One colour per stage, from the stage table (FR-004). */
const STATUS_COLOURS = Object.fromEntries(STAGES.map((s) => [s.key, s.cssVar])) as Record<
  StageKey,
  string
>

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
