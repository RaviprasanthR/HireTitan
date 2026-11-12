import { useId, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Field, inputClass } from '@/features/companies/Field'
import {
  type Interview,
  type InterviewContact,
  useInterview,
  useSaveContact,
  useSaveSource,
} from './interviewApi'

type Source = Interview['source']

function errorOf(error: unknown): ApiError | null {
  return error instanceof ApiError ? error : null
}

function Message({ error, saved }: { error: unknown; saved: string | null }) {
  const api = errorOf(error)
  // field errors are shown on their fields; anything else is shown here
  if (error && (!api || api.fieldErrors.length === 0)) {
    return (
      <p role="alert" className="text-sm text-danger">
        {error instanceof Error ? error.message : 'Could not save.'}
      </p>
    )
  }
  return saved ? (
    <p role="status" className="text-sm text-muted-small">
      {saved}
    </p>
  ) : null
}

function ContactSection({
  contact,
  editable,
  save,
}: {
  contact: InterviewContact | null
  editable: boolean
  save: ReturnType<typeof useSaveContact>
}) {
  const [name, setName] = useState(contact?.name ?? '')
  const [role, setRole] = useState(contact?.role ?? '')
  const [email, setEmail] = useState(contact?.email ?? '')
  const [phone, setPhone] = useState(contact?.phone ?? '')
  const [link, setLink] = useState(contact?.linkedin_url ?? '')
  const error = errorOf(save.error)

  return (
    <form
      aria-label="Point of contact"
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate({ name, role, email, phone, linkedin_url: link })
      }}
    >
      <h3 className="text-sm font-semibold">Point of contact</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Contact name" error={error?.fieldError('name')}>
          {(props) => (
            <input
              {...props}
              className={inputClass}
              maxLength={120}
              value={name}
              disabled={!editable}
              onChange={(e) => setName(e.target.value)}
            />
          )}
        </Field>
        <Field label="Role" error={error?.fieldError('role')}>
          {(props) => (
            <input
              {...props}
              className={inputClass}
              maxLength={120}
              value={role}
              disabled={!editable}
              onChange={(e) => setRole(e.target.value)}
            />
          )}
        </Field>
        <Field label="Email" error={error?.fieldError('email')}>
          {(props) => (
            <input
              {...props}
              className={inputClass}
              maxLength={254}
              value={email}
              disabled={!editable}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>
        <Field label="Phone" error={error?.fieldError('phone')}>
          {(props) => (
            <input
              {...props}
              className={inputClass}
              maxLength={30}
              value={phone}
              disabled={!editable}
              onChange={(e) => setPhone(e.target.value)}
            />
          )}
        </Field>
        <Field label="LinkedIn link" error={error?.fieldError('linkedin_url')}>
          {(props) => (
            <input
              {...props}
              className={inputClass}
              maxLength={500}
              value={link}
              disabled={!editable}
              onChange={(e) => setLink(e.target.value)}
            />
          )}
        </Field>
      </div>
      {editable && (
        <div className="flex items-center gap-3">
          <Button type="submit" size="sm" disabled={save.isPending}>
            Save contact
          </Button>
          <Message error={save.error} saved={save.isSuccess ? 'Contact saved.' : null} />
        </div>
      )}
    </form>
  )
}

function SourceSection({
  source,
  editable,
  save,
}: {
  source: Source
  editable: boolean
  save: ReturnType<typeof useSaveSource>
}) {
  const [kind, setKind] = useState<'direct' | 'hiring_firm' | null>(source?.kind ?? null)
  const [firm, setFirm] = useState(source?.firm_name ?? '')
  const group = useId()
  const error = errorOf(save.error)
  const choices: { value: 'direct' | 'hiring_firm' | null; label: string }[] = [
    { value: 'direct', label: 'Direct' },
    { value: 'hiring_firm', label: 'Through a hiring firm' },
    { value: null, label: 'Not set' },
  ]

  return (
    <form
      aria-label="How the job came"
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate(kind === 'hiring_firm' ? { kind, firm_name: firm } : { kind })
      }}
    >
      <h3 className="text-sm font-semibold">How the job came</h3>
      <div role="radiogroup" aria-label="Source" className="flex flex-wrap gap-4 text-sm">
        {choices.map((choice) => (
          <label key={choice.label} className="flex items-center gap-2">
            <input
              type="radio"
              name={group}
              checked={kind === choice.value}
              disabled={!editable}
              onChange={() => setKind(choice.value)}
            />
            {choice.label}
          </label>
        ))}
      </div>
      {kind === 'hiring_firm' && (
        <Field label="Firm name" error={error?.fieldError('firm_name')}>
          {(props) => (
            <input
              {...props}
              className={inputClass}
              maxLength={120}
              value={firm}
              disabled={!editable}
              onChange={(e) => setFirm(e.target.value)}
            />
          )}
        </Field>
      )}
      {error?.fieldError('kind') && (
        <p className="text-sm text-danger">{error.fieldError('kind')}</p>
      )}
      {editable && (
        <div className="flex items-center gap-3">
          <Button type="submit" size="sm" disabled={save.isPending}>
            Save source
          </Button>
          <Message error={save.error} saved={save.isSuccess ? 'Source saved.' : null} />
        </div>
      )}
    </form>
  )
}

/** What the person recorded about one pipeline job; shown in the pipeline row and on the job page. */
export function InterviewPanel({ jobId }: { jobId: string }) {
  const interview = useInterview(jobId)
  // the sections remount when the saved values change, so their save state lives here
  const saveContact = useSaveContact(jobId)
  const saveSource = useSaveSource(jobId)

  if (interview.isPending) return <p>Loading…</p>
  if (interview.isError) return <p role="alert">Could not load the details.</p>
  const data = interview.data

  return (
    <>
      <section aria-label="Interview details" className="space-y-4 border-t border-divider pt-3">
        {!data.can_edit && (
          <p className="text-sm text-muted-small">
            This job is not in your pipeline, so details can only be read. Mark it applied or
            inquired to change them.
          </p>
        )}
        <ContactSection
          key={`contact-${JSON.stringify(data.contact)}`}
          contact={data.contact}
          save={saveContact}
          editable={data.can_edit}
        />
        <SourceSection
          key={`source-${JSON.stringify(data.source)}`}
          source={data.source}
          save={saveSource}
          editable={data.can_edit}
        />
      </section>
    </>
  )
}
