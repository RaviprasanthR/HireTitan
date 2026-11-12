import { useSyncExternalStore } from 'react'

export type PipelineKind = 'applied' | 'inquired'
export type UndoNotice = { id: string; title: string; kind: PipelineKind } | null

let current: UndoNotice = null
const listeners = new Set<() => void>()

function emit() {
  for (const listener of listeners) listener()
}

/** Shows the "Marked as applied. Undo" notice for a job (one at a time). */
export function showUndo(notice: UndoNotice): void {
  current = notice
  emit()
}

export function useUndoNotice(): UndoNotice {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => current,
  )
}
