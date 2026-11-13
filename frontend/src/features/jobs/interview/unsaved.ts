import { createContext, useCallback, useContext, useEffect, useId, useMemo, useState } from 'react'

/**
 * Which forms of the interview panels hold edits that are not saved yet (FR-013). Every form
 * reports itself; a page reads the result to ask before a row closes or the page is left.
 * Ids are grouped by a scope (a job id) so one registry can serve every row of a list.
 */
export type UnsavedRegistry = {
  report: (id: string, unsaved: boolean) => void
  /** Anything unsaved anywhere on the page. */
  any: boolean
  /** Anything unsaved in the panel of this scope. */
  anyIn: (scope: string) => boolean
}

export function useUnsavedRegistry(): UnsavedRegistry {
  const [ids, setIds] = useState<ReadonlySet<string>>(new Set())
  const report = useCallback((id: string, unsaved: boolean) => {
    setIds((previous) => {
      if (previous.has(id) === unsaved) return previous
      const next = new Set(previous)
      if (unsaved) next.add(id)
      else next.delete(id)
      return next
    })
  }, [])
  return useMemo(
    () => ({
      report,
      any: ids.size > 0,
      anyIn: (scope: string) => [...ids].some((id) => id.startsWith(`${scope}|`)),
    }),
    [ids, report],
  )
}

export const UnsavedContext = createContext<((id: string, unsaved: boolean) => void) | null>(null)

/** A form tells the panel whether it holds edits that are not saved. */
export function useReportUnsaved(unsaved: boolean) {
  const report = useContext(UnsavedContext)
  const id = useId()
  useEffect(() => {
    report?.(id, unsaved)
    return () => report?.(id, false)
  }, [report, id, unsaved])
}
