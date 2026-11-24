import { useId, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { PipelineControl } from './PipelineControl'
import { InjectionWarning, type InjectionFlag } from './InjectionWarning'
import { type PastedJob, usePasteJob } from './pasteApi'
import { useMarkPipeline } from './pipelineApi'
import { ResumeSelect } from './resume/ResumeSelect'
import { useResumeOptions } from './resume/resumeApi'
import { apiFetch } from '@/api/client'

type Already = '' | 'applied' | 'inquired'

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

type FollowUp =
  | { step: 'none' }
  | { step: 'running'; mark: 'applied' | 'inquired' }
  | { step: 'done'; mark: 'applied' | 'inquired' }
  | { step: 'skipped' }
  | { step: 'failed'; message: string }

const FOLLOW_UP_NONE: FollowUp = { step: 'none' }

function FollowUpLine({ followUp }: { followUp: FollowUp }) {
  // always mounted, so each change is announced
  const said =
    followUp.step === 'running'
      ? `Recording that you ${followUp.mark}…`
      : followUp.step === 'done'
        ? `Marked as ${followUp.mark}.`
        : followUp.step === 'skipped'
          ? 'This job was already in your pipeline, so it was not marked again.'
          : ''
  return (
    <p role="status" className="text-sm">
      {said}
    </p>
  )
}

function Saved({
  job,
  followUp,
  onAnother,
  onClose,
}: {
  job: PastedJob
  followUp: FollowUp
  onAnother: () => void
  onClose: () => void
}) {
  const merged = job.merged_into !== null
  const running = followUp.step === 'running'
  const marked = followUp.step === 'done'
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
      <FollowUpLine followUp={followUp} />
      {followUp.step === 'failed' && (
        <p role="alert" className="text-sm text-danger">
          {followUp.message}
        </p>
      )}
      <InjectionWarning flags={job.injection_flags as InjectionFlag[]} />
      {job.state === 'explore' && !running && !marked && (
        <PipelineControl id={job.id} state={job.state} />
      )}
      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" disabled={running} onClick={onAnother}>
          Add another
        </Button>
        <Button type="button" variant="ghost" size="sm" disabled={running} onClick={onClose}>
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
  const [linkOnly, setLinkOnly] = useState(false)
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [location, setLocation] = useState('')
  const [already, setAlready] = useState<Already>('')
  const [resume, setResume] = useState('')
  const [contact, setContact] = useState({ name: '', role: '', email: '', phone: '', linkedin: '' })
  const [followUp, setFollowUp] = useState<FollowUp>(FOLLOW_UP_NONE)
  const files = useResumeOptions()
  const markApplied = useMarkPipeline('applied')
  const markInquired = useMarkPipeline('inquired')
  const paste = usePasteJob()
  const error = paste.error instanceof ApiError ? paste.error : null

  if (paste.isSuccess) {
    return (
      <section role="dialog" aria-label="Add a job" className="space-y-3 rounded-lg bg-surface p-4">
        <Saved
          job={paste.data}
          followUp={followUp}
          onClose={onClose}
          onAnother={() => {
            setUrl('')
            setDescription('')
            setLinkOnly(false)
            setTitle('')
            setCompany('')
            setLocation('')
            setAlready('')
            setResume('')
            setContact({ name: '', role: '', email: '', phone: '', linkedin: '' })
            setFollowUp(FOLLOW_UP_NONE)
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
          setFollowUp(FOLLOW_UP_NONE)
          void (async () => {
            let job: PastedJob
            try {
              job = await paste.mutateAsync({
                url,
                description: linkOnly ? '' : description,
                ...(title.trim() ? { title } : {}),
                ...(company.trim() ? { company } : {}),
                ...(location.trim() ? { location } : {}),
                ...(linkOnly ? { link_only: true } : {}),
              })
            } catch {
              return // the form shows the error
            }
            if (already === '') return
            if (job.state !== 'explore') {
              setFollowUp({ step: 'skipped' })
              return
            }
            setFollowUp({ step: 'running', mark: already })
            try {
              await (already === 'applied' ? markApplied : markInquired).mutateAsync({
                id: job.id,
                ...(files.data && files.data.length > 0 ? { resume: resume || null } : {}),
              })
              if (contact.name.trim()) {
                await apiFetch(`/jobs/${job.id}/interview/contact`, {
                  method: 'PUT',
                  json: {
                    name: contact.name,
                    role: contact.role || null,
                    email: contact.email || null,
                    phone: contact.phone || null,
                    linkedin_url: contact.linkedin || null,
                  },
                })
              }
              setFollowUp({ step: 'done', mark: already })
            } catch (failure) {
              setFollowUp({
                step: 'failed',
                message: `The job was added, but ${
                  failure instanceof Error ? failure.message : 'the rest could not be saved'
                }. You can record it from the job.`,
              })
            }
          })()
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
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={linkOnly}
            onChange={(event) => setLinkOnly(event.target.checked)}
          />
          I don't have the description
        </label>
        {linkOnly ? (
          <p className="text-sm text-muted-small">
            The job is saved with its link, title and company. You can add the description later
            from the job. HireTitan never opens the link.
          </p>
        ) : (
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
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={linkOnly ? 'Job title' : 'Job title (optional)'}
            error={error?.fieldError('title')}
          >
            {(props) => (
              <input
                {...props}
                required={linkOnly}
                className={input}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            )}
          </Field>
          <Field label="Location (optional)" error={error?.fieldError('location')}>
            {(props) => (
              <input
                {...props}
                className={input}
                placeholder="City, country or Remote"
                value={location}
                onChange={(event) => setLocation(event.target.value)}
              />
            )}
          </Field>
          <Field
            label={linkOnly ? 'Company' : 'Company (optional)'}
            error={error?.fieldError('company')}
          >
            {(props) => (
              <input
                {...props}
                required={linkOnly}
                className={input}
                value={company}
                onChange={(event) => setCompany(event.target.value)}
              />
            )}
          </Field>
        </div>
        <fieldset className="ht-detail-card ht-section-record space-y-3">
          <legend className="sr-only">Already applied or inquired</legend>
          <p className="ht-detail-heading !mb-0">Already applied or inquired?</p>
          <div className="flex flex-wrap gap-4 text-sm">
            {(
              [
                ['', 'Not yet'],
                ['applied', 'I applied'],
                ['inquired', 'I inquired'],
              ] as const
            ).map(([value, text]) => (
              <label key={value} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="already"
                  checked={already === value}
                  onChange={() => setAlready(value)}
                />
                {text}
              </label>
            ))}
          </div>
          {already !== '' && (
            <div className="space-y-3">
              <ResumeSelect files={files.data ?? []} value={resume} onChange={setResume} />
              <p className="text-sm font-medium">Point of contact (optional)</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {(
                  [
                    ['name', 'Name'],
                    ['role', 'Role'],
                    ['email', 'Email'],
                    ['phone', 'Phone'],
                    ['linkedin', 'LinkedIn link'],
                  ] as const
                ).map(([key, text]) => (
                  <Field key={key} label={text}>
                    {(props) => (
                      <input
                        {...props}
                        className={input}
                        value={contact[key]}
                        onChange={(event) =>
                          setContact((was) => ({ ...was, [key]: event.target.value }))
                        }
                      />
                    )}
                  </Field>
                ))}
              </div>
            </div>
          )}
        </fieldset>
        {paste.isError && error?.fieldErrors.length === 0 && (
          <p role="alert" className="text-sm text-danger">
            {paste.error.message}
          </p>
        )}
        <div className="flex gap-2">
          <Button type="submit" size="sm" disabled={paste.isPending} variant="success">
            Save job
          </Button>
          <Button type="button" variant="cancel" size="sm" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </section>
  )
}
