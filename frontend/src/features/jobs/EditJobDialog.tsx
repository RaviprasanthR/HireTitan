import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { formatDay, useJob } from '@/features/explore/api'
import { InterviewPanel } from './interview/InterviewPanel'
import type { UnsavedRegistry } from './interview/unsaved'
import { PipelineControl } from './PipelineControl'
import { useUndoPipeline } from './pipelineApi'

/**
 * A job's pipeline details in a card over the page, with the page behind it blurred: the date,
 * Undo, the contact, the source, the rounds and the questions. Closing with edits that are not
 * saved asks first (FR-013).
 */
export function EditJobDialog({
  jobId,
  title,
  registry,
  onClose,
}: {
  jobId: string
  title: string
  registry: UnsavedRegistry
  onClose: () => void
}) {
  const scope = `edit-${jobId}`
  const job = useJob(jobId)
  const undoApplied = useUndoPipeline('applied')
  const undoInquired = useUndoPipeline('inquired')
  const [asking, setAsking] = useState(false)
  const card = useRef<HTMLDivElement>(null)

  const requestClose = () => {
    if (registry.anyIn(scope)) setAsking(true)
    else onClose()
  }
  const closeRef = useRef(requestClose)
  useEffect(() => {
    closeRef.current = requestClose
  })

  useEffect(() => {
    card.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeRef.current()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const data = job.data
  const undo = data?.state === 'applied' ? undoApplied : undoInquired

  return (
    <div
      data-testid="modal-backdrop"
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-6 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) requestClose()
      }}
    >
      <div
        ref={card}
        role="dialog"
        aria-modal="true"
        aria-label={`Edit ${title}`}
        tabIndex={-1}
        className="my-auto w-full max-w-2xl space-y-4 rounded-xl bg-surface p-6 shadow-2xl outline-none"
      >
        <div className="flex items-start justify-between gap-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button
            type="button"
            className="ht-icon-button"
            aria-label="Close"
            title="Close"
            onClick={requestClose}
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>

        {asking && (
          <div role="alertdialog" aria-label="Unsaved changes" className="space-y-2">
            <p className="text-sm">You have changes that are not saved. Close and lose them?</p>
            <div className="flex gap-2">
              <Button type="button" size="sm" autoFocus onClick={onClose}>
                Close and lose them
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setAsking(false)}>
                Keep editing
              </Button>
            </div>
          </div>
        )}

        {job.isError && <p role="alert">Could not load this job.</p>}
        {data && (data.state === 'applied' || data.state === 'inquired') && (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span>
              {data.state === 'applied'
                ? `Applied on ${formatDay(data.applied_on)}`
                : `Inquired on ${formatDay(data.inquired_on)}`}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={undo.isPending}
              onClick={() => undo.mutate(data.id, { onSuccess: onClose })}
            >
              Undo
            </Button>
            {data.state === 'inquired' && (
              <PipelineControl
                id={data.id}
                state={data.state}
                ownResumeId={data.resume?.resume_file_id ?? null}
              />
            )}
          </div>
        )}

        <InterviewPanel jobId={jobId} scope={scope} registry={registry} />

        <Link to={`/jobs/${jobId}`} className="inline-block text-sm text-link underline">
          Open the full job page
        </Link>
      </div>
    </div>
  )
}
