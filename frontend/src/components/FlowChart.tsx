import type { LucideIcon } from 'lucide-react'
import { Fragment } from 'react'
import './charts.css'

export type FlowStep = {
  key: string
  icon: LucideIcon
  title: string
  value: string
  note?: string
}

const STAGGER_MS = 110

/**
 * Steps drawn as a flow chart: round nodes joined by connectors along which dashes run, left to
 * right (top to bottom on a narrow screen). The last node is the outcome and wears the accent.
 * Nodes pop in one after another and lift when pointed at; reduced motion turns the movement off.
 */
export function FlowChart({ label, steps }: { label: string; steps: FlowStep[] }) {
  return (
    <div className="flex items-center justify-center overflow-x-auto rounded-lg bg-surface p-4">
      <ol
        aria-label={label}
        className="flex w-full flex-col items-center gap-1 lg:flex-row lg:items-start lg:gap-0"
      >
        {steps.map((step, index) => {
          const Icon = step.icon
          const last = index === steps.length - 1
          return (
            <Fragment key={step.key}>
              <li
                className="ht-flow-step flex w-36 flex-none flex-col items-center text-center"
                style={{ animationDelay: `${index * STAGGER_MS}ms` }}
              >
                <span className={`ht-flow-node ${last ? 'ht-flow-node-last' : ''}`}>
                  <Icon aria-hidden className="ht-flow-icon size-6" />
                </span>
                <span className="mt-2 block text-lg font-semibold leading-tight">{step.value}</span>
                <span className="block text-sm text-muted-small">{step.title}</span>
                {step.note && <span className="block text-xs text-muted-small">{step.note}</span>}
              </li>
              {!last && (
                <li
                  aria-hidden
                  className="ht-flow-link"
                  style={{ animationDelay: `${index * STAGGER_MS + STAGGER_MS / 2}ms` }}
                />
              )}
            </Fragment>
          )
        })}
      </ol>
    </div>
  )
}

/** A flow chart and a donut side by side on a wide screen, one above the other otherwise. */
export function ChartRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid items-stretch gap-4 xl:grid-cols-[minmax(0,1fr)_auto]">{children}</div>
  )
}
