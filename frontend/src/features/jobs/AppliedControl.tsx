import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useMarkApplied } from './appliedApi'

function today(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

/** "I applied": opens a small form with the date (today unless changed) and saves it. */
export function AppliedControl({ id }: { id: string }) {
  const [open, setOpen] = useState(false)
  const [date, setDate] = useState(today)
  const mark = useMarkApplied()

  if (!open) {
    return (
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
        I applied
      </Button>
    )
  }
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        // The default day is left out so the server's own "today" is used.
        mark.mutate(
          { id, appliedOn: date === today() ? undefined : date },
          { onSuccess: () => setOpen(false) },
        )
      }}
    >
      <label className="flex flex-col gap-1 text-sm">
        Date applied
        <input
          type="date"
          required
          max={today()}
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm"
        />
      </label>
      <Button type="submit" size="sm" disabled={mark.isPending}>
        Save
      </Button>
      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>
        Cancel
      </Button>
      {mark.isError && (
        <span role="alert" className="text-sm text-danger">
          {mark.error.message}
        </span>
      )}
    </form>
  )
}
