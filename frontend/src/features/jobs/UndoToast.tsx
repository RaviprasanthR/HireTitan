import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { showUndo, useUndoNotice } from './appliedStore'
import { useUndoPipeline } from './pipelineApi'

const SHOW_FOR_MS = 10_000

/** The "marked as applied" notice with an Undo button; it goes away by itself. */
export function UndoToast() {
  const notice = useUndoNotice()
  const undoApplied = useUndoPipeline('applied')
  const undoInquired = useUndoPipeline('inquired')
  const undo = notice?.kind === 'inquired' ? undoInquired : undoApplied
  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => showUndo(null), SHOW_FOR_MS)
    return () => clearTimeout(timer)
  }, [notice])
  if (!notice) return null
  return (
    <div
      role="status"
      className="fixed bottom-4 right-4 z-50 flex items-center gap-3 rounded-lg border border-divider bg-surface p-3 text-sm shadow-lg"
    >
      <span>
        “{notice.title}” marked as {notice.kind}.
      </span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={undo.isPending}
        onClick={() => undo.mutate(notice.id)}
      >
        Undo
      </Button>
      <Button type="button" variant="ghost" size="sm" onClick={() => showUndo(null)}>
        Dismiss
      </Button>
      {undo.isError && <span className="text-danger">{undo.error.message}</span>}
    </div>
  )
}
