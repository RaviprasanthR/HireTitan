import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { AiBanner } from '@/app/AiBanner'

const STEPS = 4

/** The centred card shown instead of the app while setup is not finished (FR-037). */
export function SetupLayout({ step, children }: { step?: number; children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col text-foreground">
      <AiBanner />
      <main className="flex flex-1 items-center justify-center px-4 py-8">
        <div className="bg-surface w-full max-w-2xl space-y-6 rounded-2xl p-6 sm:p-8">
          <header className="space-y-3">
            <p className="text-lg font-semibold">HireTitan</p>
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
          AI budget and key settings
        </Link>
      </footer>
    </div>
  )
}
