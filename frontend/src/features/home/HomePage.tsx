import { Link } from 'react-router'
import { useStatus } from '@/api/useStatus'
import { useOnboarding } from '@/features/setup/useOnboarding'

type Step = {
  label: string
  done: boolean
  action: string
  to: string
  /** When set, the step cannot be started yet and this says why. */
  blocked?: string
}

export function HomePage() {
  const query = useStatus()
  const name = useOnboarding().data?.display_name
  const checklist = query.data?.checklist

  let body
  if (query.isPending) {
    body = <p>Loading…</p>
  } else if (!checklist) {
    body = <p role="alert">Could not load your setup status.</p>
  } else {
    const steps: Step[] = [
      {
        label: 'AI key found and working',
        done: checklist.key_ok,
        action: 'Check the AI key',
        to: '/settings',
      },
      {
        label: 'Resume uploaded',
        done: checklist.resume_uploaded,
        action: 'Upload your resume',
        to: '/profile',
      },
      {
        label: 'Profile confirmed',
        done: checklist.profile_confirmed,
        action: 'Confirm your profile',
        to: '/profile',
      },
      {
        label: 'Preferences saved',
        done: checklist.preferences_saved,
        action: 'Set your preferences',
        to: '/preferences',
        blocked: checklist.profile_confirmed
          ? undefined
          : 'Available after you confirm your profile.',
      },
    ]
    body = (
      <>
        <ol aria-label="Setup checklist" className="max-w-2xl space-y-3">
          {steps.map((step) => (
            <li
              key={step.label}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-surface p-4"
            >
              <span className="flex items-center gap-3">
                <span
                  className={
                    step.done ? 'font-medium text-success' : 'font-medium text-muted-small'
                  }
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
        {steps.every((s) => s.done) && <p>You are all set up.</p>}
      </>
    )
  }

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Home</h1>
      {name && <p className="text-lg">Welcome back, {name}</p>}
      {body}
    </section>
  )
}
