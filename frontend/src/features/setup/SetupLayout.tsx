import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { Link } from 'react-router'
import { AiBanner } from '@/app/AiBanner'
import { AppName } from '@/components/AppName'

const STEPS = 4

/** The centred card shown instead of the app while setup is not finished (FR-037). */
export function SetupLayout({
  step,
  closeTo,
  children,
}: {
  step?: number
  /** Shows a red cross at the card's top right that returns here (used by Settings). */
  closeTo?: string
  children: ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col text-foreground">
      <AiBanner />
      <main className="flex flex-1 items-center justify-center px-4 py-8">
        <div className="bg-surface relative w-full max-w-2xl space-y-6 rounded-2xl p-6 sm:p-8">
          {closeTo && (
            <Link
              to={closeTo}
              aria-label="Close settings"
              title="Back to setup"
              className="text-danger absolute top-4 right-4 inline-flex size-9 items-center justify-center rounded-full outline-none hover:bg-danger/15 focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X aria-hidden="true" className="size-5" strokeWidth={2.5} />
            </Link>
          )}
          <header className="space-y-3">
            <AppName className="text-3xl" />
            {step !== undefined && (
              <div className="space-y-1">
                <p className="text-sm text-muted-small">
                  Step {step} of {STEPS}
                </p>
                <div
                  role="progressbar"
                  aria-label="Setup progress"
                  aria-valuemin={1}
                  aria-valuemax={STEPS}
                  aria-valuenow={step}
                  className="h-1.5 w-full overflow-hidden rounded-full bg-divider"
                >
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${(step / STEPS) * 100}%` }}
                  />
                </div>
              </div>
            )}
          </header>
          {children}
        </div>
      </main>
      <footer className="px-4 pb-6 text-center text-sm">
        <Link to="/settings" className="text-link underline">
          AI key settings
        </Link>
      </footer>
    </div>
  )
}
