import { Link } from 'react-router'
import { useStatus } from '@/api/useStatus'
import { useOnboarding } from '@/features/setup/useOnboarding'
import { stepsFor } from './setup'

/** The setup steps, with what to do next. Shown on Home and above the job list (FR-031). */
export function SetupChecklist({ showAllSet = true }: { showAllSet?: boolean }) {
  const query = useStatus()
  const checklist = query.data?.checklist
  if (query.isPending) return <p>Loading…</p>
  if (!checklist) return <p role="alert">Could not load your setup status.</p>
  const steps = stepsFor(checklist)
  return (
    <>
      <ol aria-label="Setup checklist" className="max-w-2xl space-y-3">
        {steps.map((step) => (
          <li
            key={step.label}
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-surface p-4"
          >
            <span className="flex items-center gap-3">
              <span
                className={step.done ? 'font-medium text-success' : 'font-medium text-muted-small'}
              >
                {step.done ? 'Done' : 'To do'}
              </span>
              <span>{step.label}</span>
            </span>
            {!step.done &&
              (step.blocked ? (
                <span className="text-sm text-muted-small">{step.blocked}</span>
              ) : (
                <Link to={step.to} className="text-sm font-medium text-link underline">
                  {step.action}
                </Link>
              ))}
          </li>
        ))}
      </ol>
      {showAllSet && steps.every((s) => s.done) && <p>You are all set up.</p>}
    </>
  )
}

export function HomePage() {
  const name = useOnboarding().data?.display_name
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Home</h1>
      {name && <p className="text-lg">Welcome back, {name}</p>}
      <SetupChecklist />
    </section>
  )
}
