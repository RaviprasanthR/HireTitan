import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { ChangeData } from './stream'

/** A change Mikasa made at once, with the Undo the page would offer (FR-014). */
export function ChangeNotice({
  change,
  onUndo,
}: {
  change: ChangeData
  onUndo: (changeId: string) => Promise<void>
}) {
  const [undone, setUndone] = useState(change.undone ?? false)
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [shownAt] = useState(() => Date.now()) // the Undo window is judged from when it appeared
  const canUndo =
    !undone && change.undo_until !== null && new Date(change.undo_until).getTime() > shownAt
  return (
    <div
      role="status"
      className="mikasa-rise my-2 ml-9 flex flex-wrap items-center gap-2 rounded-xl border border-slate bg-background/60 p-2 text-xs"
    >
      <span className="flex-1">{undone ? 'Undone.' : (change.summary ?? 'Done.')}</span>
      {canUndo && (
        <Button
          type="button"
          size="xs"
          variant="outline"
          disabled={busy}
          onClick={() => {
            setBusy(true)
            setProblem(null)
            onUndo(change.change_id)
              .then(() => setUndone(true))
              .catch((error: unknown) =>
                setProblem(error instanceof Error ? error.message : 'Undo did not work.'),
              )
              .finally(() => setBusy(false))
          }}
        >
          {busy && <Loader2 aria-hidden className="animate-spin" />}
          Undo
        </Button>
      )}
      {problem && (
        <p role="alert" className="w-full text-danger">
          {problem}
        </p>
      )}
    </div>
  )
}
