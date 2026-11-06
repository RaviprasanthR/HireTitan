import { useId, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { AppliedControl } from './AppliedControl'
import { InjectionWarning, type InjectionFlag } from './InjectionWarning'
import { type PastedJob, usePasteJob } from './pasteApi'

const input = 'w-full rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm'

function Field({
  label,
  error,
  children,
}: {
  label: string
  error?: string
  children: (props: {
    id: string
    'aria-describedby'?: string
    'aria-invalid'?: boolean
  }) => React.ReactNode
}) {
  const id = useId()
  const errorId = `${id}-error`
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children({
        id,
        'aria-describedby': error ? errorId : undefined,
        'aria-invalid': error ? true : undefined,
      })}
      {error && (
        <p id={errorId} className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  )
}

function Saved({
  job,
  onAnother,
  onClose,
}: {
  job: PastedJob
  onAnother: () => void
  onClose: () => void
}) {
  const merged = job.merged_into !== null
  return (
    <div className="space-y-3">
      <p>
        {merged
          ? 'This job was already in your jobs, so the link was added as another source.'
          : 'Added to your jobs.'}
      </p>
      <p>
        <Link to={`/jobs/${job.id}`} className="font-semibold text-link underline">
          {job.title}
        </Link>
        <span className="text-sm text-muted-small"> · {job.company_name}</span>
      </p>
      <InjectionWarning flags={job.injection_flags as InjectionFlag[]} />
      {job.state === 'explore' && <AppliedControl id={job.id} />}
      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onAnother}>
          Add another
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          Done
        </Button>
      </div>
    </div>
  )
}

/** Add a job by hand: the link and the pasted description. No AI is involved (FR-033). */
export function PasteJobDialog({ onClose }: { onClose: () => void }) {
  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const paste = usePasteJob()
  const error = paste.error instanceof ApiError ? paste.error : null

  if (paste.isSuccess) {
    return (
      <section role="dialog" aria-label="Add a job" className="space-y-3 rounded-lg bg-surface p-4">
        <Saved
          job={paste.data}
          onClose={onClose}
          onAnother={() => {
            setUrl('')
            setDescription('')
            setTitle('')
            setCompany('')
            paste.reset()
          }}
        />
      </section>
    )
  }

  return (
    <section role="dialog" aria-label="Add a job" className="space-y-3 rounded-lg bg-surface p-4">
      <h2 className="text-lg font-semibold">Add a job</h2>
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          paste.mutate({
            url,
            description,
            ...(title.trim() ? { title } : {}),
            ...(company.trim() ? { company } : {}),
          })
        }}
      >
        <Field label="Link to the job" error={error?.fieldError('url')}>
          {(props) => (
            <input
              {...props}
              className={input}
              inputMode="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
            />
          )}
        </Field>
        <Field label="Job description" error={error?.fieldError('description')}>
          {(props) => (
            <textarea
              {...props}
              className={`${input} min-h-40`}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          )}
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Job title (optional)" error={error?.fieldError('title')}>
            {(props) => (
              <input
                {...props}
                className={input}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            )}
          </Field>
          <Field label="Company (optional)" error={error?.fieldError('company')}>
            {(props) => (
              <input
                {...props}
                className={input}
                value={company}
                onChange={(event) => setCompany(event.target.value)}
              />
            )}
          </Field>
        </div>
        {paste.isError && error?.fieldErrors.length === 0 && (
          <p role="alert" className="text-sm text-danger">
            {paste.error.message}
          </p>
        )}
        <div className="flex gap-2">
          <Button type="submit" size="sm" disabled={paste.isPending}>
            Save job
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </section>
  )
}
