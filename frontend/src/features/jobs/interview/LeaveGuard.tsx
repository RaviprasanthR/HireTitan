import { useContext, useEffect } from 'react'
import { UNSAFE_DataRouterContext, useBlocker } from 'react-router'
import { Button } from '@/components/ui/button'

/** Closing the tab or reloading asks too, whatever the router. */
function useBeforeUnload(when: boolean) {
  useEffect(() => {
    if (!when) return
    const ask = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', ask)
    return () => window.removeEventListener('beforeunload', ask)
  }, [when])
}

function RouterBlocker({ when }: { when: boolean }) {
  const blocker = useBlocker(when)
  if (blocker.state !== 'blocked') return null
  return (
    <div
      role="alertdialog"
      aria-label="Unsaved changes"
      className="space-y-2 rounded-lg bg-surface p-4"
    >
      <p>You have changes that are not saved. Leave this page and lose them?</p>
      <div className="flex gap-2">
        <Button type="button" size="sm" onClick={() => blocker.proceed()}>
          Leave and lose them
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => blocker.reset()}>
          Stay on this page
        </Button>
      </div>
    </div>
  )
}

/** Asks before the page is left while an interview form holds unsaved edits (FR-013). */
export function LeaveGuard({ when }: { when: boolean }) {
  useBeforeUnload(when)
  // the blocker needs the app's data router; a bare router (some tests) only gets beforeunload
  const dataRouter = useContext(UNSAFE_DataRouterContext)
  return dataRouter ? <RouterBlocker when={when} /> : null
}
