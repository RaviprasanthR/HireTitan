import { BadgeCheck, CalendarClock, MessageCircleQuestion, Send } from 'lucide-react'
import { FlowChart } from '@/components/FlowChart'
import { Donut } from '@/components/Donut'
import { STAGES } from '@/theme/stages'
import { usePipelineSummary } from './api'

/** The pipeline at a glance, beside the In pipeline list (FR-023a): the flow from inquired to a
 * cleared round with "In pipeline" as its total and the largest stage marked (FR-024), then every
 * job by its stage as a donut (clarification 2026-11-26). Nothing until something is in the pipeline. */
export function PipelineChart() {
  const summary = usePipelineSummary()
  const s = summary.data
  if (!s || s.total === 0) return null
  const steps = [
    { key: 'inquired', icon: MessageCircleQuestion, title: 'Inquired', value: s.inquired },
    { key: 'applied', icon: Send, title: 'Applied', value: s.applied },
    { key: 'scheduled', icon: CalendarClock, title: 'Interview scheduled', value: s.scheduled },
    { key: 'cleared', icon: BadgeCheck, title: 'Round cleared', value: s.cleared },
  ] as const
  const largest = steps.reduce((best, step) => (step.value > best.value ? step : best))
  return (
    <>
      <FlowChart
        label="Your pipeline"
        total={{ label: 'In pipeline', value: String(s.total) }}
        emphasis={largest.value > 0 ? largest.key : undefined}
        steps={steps.map((step) => ({
          ...step,
          stage: step.key,
          value: String(step.value),
          note: step.key === 'cleared' && s.failed > 0 ? `${s.failed} failed` : undefined,
        }))}
      />
      <Donut
        compact
        quietCentre
        caption="Your jobs by status"
        totalLabel="jobs in pipeline"
        ariaLabel={STAGES.map((stage) => `${s[stage.key]} ${stage.label.toLowerCase()}`).join(', ')}
        parts={STAGES.map((stage) => ({
          key: stage.key,
          label: stage.label,
          value: s[stage.key],
          colour: stage.cssVar,
        }))}
      />
    </>
  )
}
