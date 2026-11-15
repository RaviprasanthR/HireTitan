import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useMarkPipeline } from './pipelineApi'
import { ResumeSelect } from './resume/ResumeSelect'
import { usePipelineResumes, useResumeOptions } from './resume/resumeApi'

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
 *
 * Beside the date, an optional "Resume used" choice (feature 002f) names the stored resume file
 * the person used. It starts on the job's own resume when it has one (`ownResumeId`, an inquired
 * job), else on the resume chosen the last time a job was marked, else None, and it is not shown
 * when there is no file to choose. Leaving it alone keeps marking a single click.
 */
export function PipelineControl({
  id,
  state,
  ownResumeId,
}: {
  id: string
  state: string
  ownResumeId?: string | null
}) {
  const [custom, setCustom] = useState(false)
  const [date, setDate] = useState(today)
  const [picked, setPicked] = useState<string | undefined>(undefined)
  const files = useResumeOptions()
  const pipeline = usePipelineResumes()
  const applied = useMarkPipeline('applied')
  const inquired = useMarkPipeline('inquired')
  if (state === 'applied' || state === 'deleted') return null

  const offered = files.data ?? []
  const showResume = files.isSuccess && pipeline.isSuccess && offered.length > 0
  const stillStored = (fileId: string | null | undefined) =>
    fileId && offered.some((file) => file.id === fileId) ? fileId : undefined
  const start = stillStored(ownResumeId) ?? stillStored(pipeline.data?.last_choice) ?? ''
  const resumeValue = picked ?? start
  // not shown: leave the field out, so the server changes nothing about the resume
  const resume = showResume ? resumeValue || null : undefined

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
      {showResume && (
        <ResumeSelect
          files={offered}
          value={resumeValue}
          onChange={setPicked}
          disabled={busy}
        />
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={() => applied.mutate({ id, day, resume })}
      >
        I applied
      </Button>
      {state !== 'inquired' && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => inquired.mutate({ id, day, resume })}
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
