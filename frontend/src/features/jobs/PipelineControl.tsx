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
 * "I applied" and "I inquired": one click marks the job with today's date. "Pick a date" shows a
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
  ownRemoved = false,
  title,
  className = '',
  compact = false,
}: {
  id: string
  state: string
  /**
   * A list row: only "I applied" and "I inquired", one click each. The resume choice and the date
   * stay out of sight, but the starting resume is still sent, so nothing is lost (feature 002k).
   */
  compact?: boolean
  /** Extra classes for the row of controls (a list row right-aligns them). */
  className?: string
  /** The job's title, so the choice is named for it where a page lists many jobs. */
  title?: string
  /** The job's own resume file, `null` for none; left out while it is not known. */
  ownResumeId?: string | null
  /** The job's resume file was removed and only its name is left as a note. */
  ownRemoved?: boolean
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
  const stillStored = (fileId: string | null | undefined) =>
    fileId && offered.some((file) => file.id === fileId) ? fileId : undefined
  // An inquired job may already have a resume. Until the caller says which (`ownResumeId`, null
  // for none), the choice is not shown and nothing is sent, so one click cannot overwrite it.
  const ownKnown = state !== 'inquired' || ownResumeId !== undefined
  // The last choice failing to load must not take the choice away: it then starts on None.
  const startKnown = pipeline.isSuccess || pipeline.isError
  const showResume = ownKnown && files.isSuccess && startKnown && offered.length > 0
  // A removed file's note is the job's resume until the person chooses: the choice starts on
  // None rather than on the last choice, and untouched it sends nothing, so the note stays.
  const start = ownRemoved
    ? ''
    : (stillStored(ownResumeId) ?? stillStored(pipeline.data?.last_choice) ?? '')
  // A picked file that has been removed since is no longer sent: the select shows the start again.
  const resumeValue = picked === '' || stillStored(picked) ? (picked ?? start) : start
  // not shown: leave the field out, so the server changes nothing about the resume
  const keepsNote = ownRemoved && picked === undefined
  const resume = showResume && !keepsNote ? resumeValue || null : undefined

  // The default day is left out so the server's own "today" is used.
  const day = custom && date !== today() ? date : undefined
  const error = applied.isError ? applied.error : inquired.isError ? inquired.error : null
  const busy = applied.isPending || inquired.isPending
  // a cleared date would silently become today on the server: ask for one instead
  const blocked = busy || (custom && date === '')
  // in a list every row has the same buttons, so say which job they are for
  const forId = compact && title ? `pipeline-for-${id}` : undefined
  return (
    <div className={`flex flex-wrap items-end gap-2 ${className}`}>
      {forId && (
        <span id={forId} className="sr-only">
          {`For: ${title}`}
        </span>
      )}
      {custom && !compact && (
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
      {showResume && !compact && (
        <ResumeSelect
          ariaLabel={title ? `Resume used for ${title}` : undefined}
          files={offered}
          value={resumeValue}
          onChange={setPicked}
          disabled={busy}
        />
      )}
      <Button
        type="button"
        variant="success"
        size="sm"
        disabled={blocked}
        aria-describedby={forId}
        onClick={() => {
          inquired.reset() // an old refusal of the other mark is not shown beside a new one
          applied.mutate({ id, day, resume })
        }}
      >
        I applied
      </Button>
      {state !== 'inquired' && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={blocked}
          aria-describedby={forId}
          onClick={() => {
            applied.reset()
            inquired.mutate({ id, day, resume })
          }}
        >
          I inquired
        </Button>
      )}
      {!custom && !compact && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-muted-small"
          onClick={() => setCustom(true)}
        >
          Pick a date
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
