import { type UseQueryResult, useQuery, useQueryClient } from '@tanstack/react-query'
import { Dialog } from 'radix-ui'
import { type DragEvent, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '@/api/client'
import { ProgressBar, type ProgressTone } from '@/components/ProgressBar'
import { Button } from '@/components/ui/button'
import {
  type Accepted,
  type Decision,
  type ResumeFile,
  type Run,
  MAX_UPLOAD_BYTES,
  decide,
  fetchResumes,
  fetchRun,
  injectionFlags,
  retryRun,
  uploadResume,
} from './api'
import { ResumeFiles } from './ResumeFiles'

const PAUSE_MESSAGES: Record<string, string> = {
  key_missing:
    'No AI key is set. Add OPENAI_API_KEY to your .env file and restart; this will continue by itself.',
  key_rejected:
    'The AI provider rejected your key. Fix OPENAI_API_KEY in your .env file and restart; this will continue by itself.',
  out_of_credit:
    'Your AI account is out of credit. Add credit with your provider, then press Check again in the banner at the top; this will continue.',
}

const FINAL = new Set(['done', 'failed', 'cancelled'])

type Pending = { action: (discard: boolean) => Promise<Accepted> }
type Conflict = { openReviewId: string; again: Pending }

/**
 * What the bar shows. The inner steps (reading, screening, extracting) are not shown: a person
 * only needs to know it is working, ready, paused or failed. Busy is an unknown-length sweep.
 */
function runProgress(run: Run): {
  value: number | null
  tone: ProgressTone
  animated: boolean
  message: string
} {
  const ready =
    run.status === 'done' ||
    (run.status === 'awaiting_review' && run.waiting_for === 'profile_review')
  if (run.status === 'failed') {
    return { value: 100, tone: 'danger', animated: false, message: 'Could not read your resume.' }
  }
  if (run.status === 'paused') {
    return { value: 100, tone: 'warning', animated: false, message: 'Waiting.' }
  }
  if (ready) {
    return {
      value: 100,
      tone: 'success',
      animated: false,
      message: 'Your profile is ready to review.',
    }
  }
  return { value: null, tone: 'success', animated: false, message: 'Reading your resume…' }
}

function newestOf(files: ResumeFile[]): ResumeFile | undefined {
  return [...files].sort((x, y) => y.created_at.localeCompare(x.created_at))[0]
}

type ProfilePageProps = {
  pollMs?: number
  /** Inside a setup card: no page heading or side links (the card supplies them). */
  embedded?: boolean
  /** A resume import that was started earlier (setup returns to it after a reload). */
  resumeRunId?: string | null
  /** Replaces the "Fill in by hand" link: starts a typed-in profile instead. */
  onTypeItIn?: () => void
}

export function ProfilePage({
  pollMs = 3000,
  embedded = false,
  resumeRunId = null,
  onTypeItIn,
}: ProfilePageProps) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [accepted, setAccepted] = useState<Accepted | null>(null)
  const [conflict, setConflict] = useState<Conflict | null>(null)
  const [busy, setBusy] = useState(false)

  const resumesQuery: UseQueryResult<ResumeFile[]> = useQuery({
    queryKey: ['resumes'],
    queryFn: fetchResumes,
    refetchInterval: (q) => {
      const watched = accepted?.run_id ?? resumeRunId
      if (!watched) return false
      const files = q.state.data ?? []
      const file = accepted ? files.find((f) => f.id === accepted.resume_file_id) : newestOf(files)
      const runNow = queryClient.getQueryData<Run>(['runs', watched])
      return file?.open_review_id || (runNow && FINAL.has(runNow.status)) ? false : pollMs
    },
  })
  // After a reload the run comes from saved state; its file is the newest upload.
  const newestFile = newestOf(resumesQuery.data ?? [])
  const current: Accepted | null =
    accepted ?? (resumeRunId ? { run_id: resumeRunId, resume_file_id: newestFile?.id ?? '' } : null)
  const runId = current?.run_id
  const runQuery: UseQueryResult<Run> = useQuery({
    queryKey: ['runs', runId],
    queryFn: () => fetchRun(runId ?? ''),
    enabled: current !== null,
    refetchInterval: (q) => (q.state.data && FINAL.has(q.state.data.status) ? false : pollMs),
  })
  const run: Run | undefined = runQuery.data
  const file = resumesQuery.data?.find((f) => f.id === current?.resume_file_id)
  const highFlags = injectionFlags(file).filter(
    (f) => f.severity === 'high' && f.location === 'visible',
  )

  async function submit(pending: Pending, discard = false) {
    setError(null)
    setConflict(null)
    setBusy(true)
    try {
      const result = await pending.action(discard)
      setAccepted(result)
      await queryClient.invalidateQueries({ queryKey: ['resumes'] })
      await queryClient.invalidateQueries({ queryKey: ['onboarding'] })
    } catch (e) {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        typeof e.problem.open_review_id === 'string'
      ) {
        setConflict({ openReviewId: e.problem.open_review_id, again: pending })
      } else if (e instanceof ApiError) {
        setError(e.detail)
      } else {
        setError('Something went wrong. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  function chooseFile(chosen: File | undefined) {
    if (!chosen) return
    if (chosen.size > MAX_UPLOAD_BYTES) {
      setError('That file is larger than 5 MB. Choose a smaller PDF or DOCX.')
      return
    }
    void submit({ action: (discard) => uploadResume(chosen, discard) })
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    if (busy) return
    chooseFile(event.dataTransfer.files[0])
  }

  async function runAction(action: (runId: string) => Promise<unknown>) {
    if (!current) return
    setActionError(null)
    try {
      await action(current.run_id)
      await queryClient.invalidateQueries({
        queryKey: ['runs', current.run_id],
      })
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : 'Something went wrong. Please try again.')
    }
  }

  const answer = (decision: Decision) => runAction((id) => decide(id, decision))
  const tryAgain = () => runAction((id) => retryRun(id))

  const noText = run?.status === 'done' && file?.parse_status === 'no_text'
  const notResume = run?.status === 'done' && file?.parse_status === 'not_resume'
  const reviewId = file?.open_review_id
  const sending = run === undefined && (busy || accepted !== null)
  const progress = run ? runProgress(run) : null

  return (
    <section className={embedded ? 'space-y-6' : 'max-w-2xl space-y-6'}>
      {!embedded && (
        <>
          <h1 className="text-2xl font-semibold">Profile</h1>
          <p className="text-muted-small">
            Add your resume and HireTitan turns it into a profile you can check and edit. Nothing is
            saved as your profile until you confirm it.
          </p>
        </>
      )}

      <label
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-muted-foreground p-8 text-center focus-within:ring-2 focus-within:ring-ring"
      >
        <span className="font-medium">Resume file</span>
        <span className="text-sm text-muted-small">
          PDF or DOCX, up to 5 MB. Drop it here or click to choose.
        </span>
        <input
          type="file"
          aria-label="Resume file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="sr-only"
          disabled={busy}
          onChange={(e) => {
            chooseFile(e.target.files?.[0])
            e.target.value = ''
          }}
        />
      </label>

      {!embedded && (
        <p className="space-x-4">
          <Link to="/profile/edit" className="text-link underline">
            Fill in by hand
          </Link>
          <Link to="/profile/versions" className="text-link underline">
            Version history
          </Link>
        </p>
      )}

      {!embedded && <ResumeFiles />}

      {error && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {error}
        </p>
      )}

      {sending && (
        <div className="space-y-3 rounded-lg bg-surface p-4">
          <p className="text-sm font-medium">Uploading your resume…</p>
          <ProgressBar label="Uploading your resume" value={null} />
        </div>
      )}

      {run && progress && (
        <div className="space-y-3 rounded-lg bg-surface p-4">
          <p className="text-sm font-medium">{progress.message}</p>
          <ProgressBar
            label="Resume progress"
            value={progress.value}
            tone={progress.tone}
            animated={progress.animated}
          />
          {run.status === 'failed' && (
            <div className="space-y-2">
              <p className="text-danger">{run.error ?? 'Something went wrong.'}</p>
              <Button onClick={() => void tryAgain()}>Try again</Button>
            </div>
          )}
          {run.status === 'paused' && run.pause_reason && (
            <p className="text-warning">
              {PAUSE_MESSAGES[run.pause_reason] ?? 'This run is paused.'}
            </p>
          )}
          {reviewId && run.status === 'awaiting_review' && run.waiting_for === 'profile_review' && (
            <Link
              to={`/profile/review/${reviewId}`}
              className="inline-block rounded-md bg-primary px-4 py-2 text-primary-foreground"
            >
              Review your profile
            </Link>
          )}
        </div>
      )}

      {notResume && (
        <div role="status" className="space-y-3 rounded-lg border border-warning p-4">
          <p>
            This doesn&apos;t look like a resume, so it was not used. Upload your resume as a PDF
            or DOCX, or fill in your profile by hand.
          </p>
          <div className="flex gap-3">
            {onTypeItIn ? (
              <Button variant="secondary" onClick={onTypeItIn}>
                Type it in myself
              </Button>
            ) : (
              <Link to="/profile/edit" className="self-center text-link underline">
                Fill in by hand
              </Link>
            )}
          </div>
        </div>
      )}

      {noText && (
        <div role="status" className="space-y-3 rounded-lg border border-warning p-4">
          <p>
            We couldn&apos;t find readable text in that file. It may be a scanned image. You can
            upload a text-based PDF or DOCX, or fill in your profile by hand.
          </p>
          <div className="flex gap-3">
            {onTypeItIn ? (
              <Button variant="secondary" onClick={onTypeItIn}>
                Type it in myself
              </Button>
            ) : (
              <Link to="/profile/edit" className="self-center text-link underline">
                Fill in by hand
              </Link>
            )}
          </div>
        </div>
      )}

      <Dialog.Root open={run?.waiting_for === 'injection_decision'}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/60" />
          <Dialog.Content
            onEscapeKeyDown={(e) => e.preventDefault()}
            onPointerDownOutside={(e) => e.preventDefault()}
            className="fixed top-1/2 left-1/2 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-lg bg-surface p-6"
          >
            <Dialog.Title className="text-lg font-semibold">
              This resume contains text that looks like instructions to an AI
            </Dialog.Title>
            <Dialog.Description className="text-sm text-muted-small">
              Text like this can be used to manipulate AI tools. Check what was found, then choose
              how to continue. It will not be followed either way.
            </Dialog.Description>
            {highFlags.length === 0 && (
              <p className="text-sm">The flagged text is still loading. You can wait a moment.</p>
            )}
            {actionError && (
              <p role="alert" className="text-sm text-danger">
                {actionError}
              </p>
            )}
            <ul className="space-y-2">
              {highFlags.map((flag, i) => (
                <li key={i} className="rounded-md bg-background p-2 text-sm">
                  {flag.excerpt}
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => void answer('continue_extraction')}>
                Continue extraction
              </Button>
              <Button variant="secondary" onClick={() => void answer('manual_entry')}>
                Fill in by hand instead
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={conflict !== null} onOpenChange={(open) => !open && setConflict(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/60" />
          <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-lg bg-surface p-6">
            <Dialog.Title className="text-lg font-semibold">A review is already open</Dialog.Title>
            <Dialog.Description className="text-sm text-muted-small">
              You have a profile review in progress. Finish it first, or replace it with this
              resume. Replacing it discards the unsaved review.
            </Dialog.Description>
            <div className="flex flex-wrap items-center gap-3">
              {conflict && (
                <Link
                  to={`/profile/review/${conflict.openReviewId}`}
                  className="text-link underline"
                >
                  Go to the open review
                </Link>
              )}
              <Button onClick={() => conflict && void submit(conflict.again, true)}>
                Replace it
              </Button>
              <Button variant="secondary" onClick={() => setConflict(null)}>
                Cancel
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  )
}
