import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useMarkPipeline } from './pipelineApi'

function today(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

/**
 * "I applied" and "I inquired": one click marks the job with today's date. "Other date" shows a
 * date field first, for when it happened on another day. A job already inquired offers only
 * "I applied"; an applied job offers neither.
 */
export function PipelineControl({ id, state }: { id: string; state: string }) {
  const [custom, setCustom] = useState(false)
  const [date, setDate] = useState(today)
  const applied = useMarkPipeline('applied')
  const inquired = useMarkPipeline('inquired')
  if (state === 'applied' || state === 'deleted') return null

  // The default day is left out so the server's own "today" is used.
  const day = custom && date !== today() ? date : undefined
  const error = applied.isError ? applied.error : inquired.isError ? inquired.error : null
  const busy = applied.isPending || inquired.isPending
  return (
    <div className="flex flex-wrap items-end gap-2">
      {custom && (
        <label className="flex flex-col gap-1 text-sm">
          Date
          <input
            type="date"
            max={today()}
            value={date}
            onChange={(event) => setDate(event.target.value)}
            className="rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm"
          />
        </label>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={() => applied.mutate({ id, day })}
      >
        I applied
      </Button>
      {state !== 'inquired' && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => inquired.mutate({ id, day })}
        >
          I inquired
        </Button>
      )}
      {!custom && (
        <Button type="button" variant="ghost" size="sm" onClick={() => setCustom(true)}>
          Other date
        </Button>
      )}
      {error && (
        <span role="alert" className="text-sm text-danger">
          {error.message}
        </span>
      )}
    </div>
  )
}
