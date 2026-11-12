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

function Message({
  error,
  saved,
  fields,
}: {
  error: unknown
  saved: string | null
  /** The fields this form shows an error for; an error about any other field is shown here. */
  fields: string[]
}) {
  const api = errorOf(error)
  // field errors are shown on their fields; anything else is shown here
  if (error && (!api || !api.fieldErrors.some((e) => fields.includes(e.field)))) {
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
  // after an edit the last result (saved, or a field error) no longer describes the form
  const [dirty, setDirty] = useState(false)
  const result = dirty ? null : save
  const error = errorOf(result?.error)
  const typed = (setter: (value: string) => void) => (value: string) => {
    setter(value)
    setDirty(true)
  }
  const onName = typed(setName)
  const onRole = typed(setRole)
  const onEmail = typed(setEmail)
  const onPhone = typed(setPhone)
  const onLink = typed(setLink)

  return (
    <form
      aria-label="Point of contact"
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault()
        setDirty(false)
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
              onChange={(e) => onName(e.target.value)}
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
              onChange={(e) => onRole(e.target.value)}
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
              onChange={(e) => onEmail(e.target.value)}
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
              onChange={(e) => onPhone(e.target.value)}
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
              onChange={(e) => onLink(e.target.value)}
            />
          )}
        </Field>
      </div>
      {editable && (
        <div className="flex items-center gap-3">
          <Button type="submit" size="sm" disabled={save.isPending}>
            Save contact
          </Button>
          <Message
            error={result?.error}
            saved={result?.isSuccess ? 'Contact saved.' : null}
            fields={['name', 'role', 'email', 'phone', 'linkedin_url']}
          />
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
  const [dirty, setDirty] = useState(false)
  const result = dirty ? null : save
  const error = errorOf(result?.error)
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
        setDirty(false)
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
              onChange={() => {
                setKind(choice.value)
                setDirty(true)
              }}
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
              onChange={(e) => {
                setFirm(e.target.value)
                setDirty(true)
              }}
            />
          )}
        </Field>
      )}
      {error?.fieldError('kind') && (
        <p role="alert" className="text-sm text-danger">
          {error.fieldError('kind')}
        </p>
      )}
      {editable && (
        <div className="flex items-center gap-3">
          <Button type="submit" size="sm" disabled={save.isPending}>
            Save source
          </Button>
          <Message
            error={result?.error}
            saved={result?.isSuccess ? 'Source saved.' : null}
            fields={kind === 'hiring_firm' ? ['kind', 'firm_name'] : ['kind']}
          />
        </div>
      )}
    </form>
  )
}

/** What the person recorded about one pipeline job; shown in the pipeline row and on the job page. */
export function InterviewPanel({
  jobId,
  heading,
  hideWhenEmpty = false,
}: {
  jobId: string
  /** A title above the panel (the job page has one; the pipeline row does not). */
  heading?: string
  /** Show nothing for a job outside the pipeline that has no details to read. */
  hideWhenEmpty?: boolean
}) {
  const interview = useInterview(jobId)
  // the sections remount when the saved values change, so their save state lives here
  const saveContact = useSaveContact(jobId)
  const saveSource = useSaveSource(jobId)

  if (interview.isPending) return <p>Loading…</p>
  if (interview.isError) {
    // a job outside the pipeline with nothing to show stays quiet
    return hideWhenEmpty ? null : <p role="alert">Could not load the details.</p>
  }
  const data = interview.data
  if (hideWhenEmpty && !data.can_edit && !data.contact && !data.source && data.rounds.length === 0)
    return null

  return (
    <>
      <section aria-label="Interview details" className="space-y-4 border-t border-divider pt-3">
        {heading && <h2 className="text-lg font-semibold">{heading}</h2>}
        {!data.can_edit && (
          <p className="text-sm text-muted-small">
            This job is not in your pipeline, so details can only be read. Mark it applied or
            inquired to change them.
          </p>
        )}
        <ContactSection
          key={`contact-${JSON.stringify(data.contact)}-${saveContact.isSuccess ? saveContact.submittedAt : 0}`}
          contact={data.contact}
          save={saveContact}
          editable={data.can_edit}
        />
        <SourceSection
          key={`source-${JSON.stringify(data.source)}-${saveSource.isSuccess ? saveSource.submittedAt : 0}`}
          source={data.source}
          save={saveSource}
          editable={data.can_edit}
        />
      </section>
    </>
  )
}
