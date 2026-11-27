import type { LucideIcon } from 'lucide-react'
import { Fragment } from 'react'
import type { StageKey } from '@/theme/stages'
import './charts.css'

export type FlowStep = {
  key: string
  icon: LucideIcon
  title: string
  value: string
  note?: string
  /** Colours the step's icon with its stage colour (DESIGN.md, Data display). */
  stage?: StageKey
}

/**
 * Steps drawn as a flow: each step is an icon and its name, with the count below in the figure face,
 * joined by a hairline, left to right (top to bottom on a narrow screen). A step with a zero count
 * is muted; the step named by `emphasis` carries the accent; `total` sits beside the flow, not in it.
 */
export function FlowChart({
  label,
  steps,
  emphasis,
  total,
}: {
  label: string
  steps: FlowStep[]
  emphasis?: string
  total?: { label: string; value: string }
}) {
  // laid out by its own width, not the window's: a column in the overview, a row when wide
  return (
    <div className="@container min-w-0">
      <div className="flex min-w-0 flex-col gap-4 rounded-[var(--ht-radius-card)] bg-surface p-5 @3xl:flex-row @3xl:items-center">
        {total && (
          <div className="flex-none @3xl:border-r @3xl:border-hairline @3xl:pr-6">
            <span className="ht-figure block text-3xl font-medium">{total.value}</span>
            <span className="block text-sm text-subtle">{total.label}</span>
          </div>
        )}
        <ol
          aria-label={label}
          className="flex w-full flex-col gap-2 @3xl:flex-row @3xl:items-start @3xl:gap-0"
        >
          {steps.map((step, index) => {
            const Icon = step.icon
            const last = index === steps.length - 1
            const muted = step.value === '0'
            return (
              <Fragment key={step.key}>
                <li
                  className="ht-flow-step flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 @3xl:block @3xl:flex-[1_1_6rem]"
                  data-stage={step.stage}
                  data-muted={muted || undefined}
                  data-emphasis={step.key === emphasis || undefined}
                >
                  <span className="flex items-center gap-2 text-sm text-subtle">
                    <Icon aria-hidden className="ht-flow-icon size-4 flex-none" />
                    {step.title}
                  </span>
                  <span className="ht-figure ht-flow-value text-xl leading-tight @3xl:mt-1 @3xl:block @3xl:text-2xl">
                    <Figure text={step.value} />
                  </span>
                  {step.note && (
                  <span className="block basis-full text-xs text-muted-small">{step.note}</span>
                )}
                </li>
                {!last && <li aria-hidden className="ht-flow-link" />}
              </Fragment>
            )
          })}
        </ol>
      </div>
    </div>
  )
}

/** A flow chart and what goes with it, side by side on a wide screen, stacked otherwise. */
export function ChartRow({ children }: { children: React.ReactNode }) {
  return <div className="grid items-stretch gap-4">{children}</div>
}

/** Mono only on the leading number: "0 left out" keeps its words in the body font. */
function Figure({ text }: { text: string }) {
  const m = /^(\d+)(.*)$/.exec(text)
  return m ? (
    <>
      <span className="ht-figure">{m[1]}</span>
      {m[2]}
    </>
  ) : (
    <>{text}</>
  )
}
